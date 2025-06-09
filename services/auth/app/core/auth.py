"""
JWT Authentication for InvoiceFlow Auth Service
Handles JWT creation, validation, and security
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger, log_auth_event, log_error
from app.models.user import User, TokenData

logger = get_logger("auth.jwt")
security = HTTPBearer()


class AuthenticationError(Exception):
    """Custom authentication error."""
    pass


class JWTManager:
    """Manages JWT token creation and validation."""
    
    def __init__(self):
        self.secret_key = settings.jwt_secret
        self.algorithm = settings.jwt_algorithm
        self.expiration_minutes = settings.jwt_expiration_minutes
    
    def create_access_token(self, data: Dict[str, Any]) -> str:
        """Create JWT access token."""
        try:
            to_encode = data.copy()
            expire = datetime.utcnow() + timedelta(minutes=self.expiration_minutes)
            
            # Add standard JWT claims
            to_encode.update({
                "exp": expire,
                "iat": datetime.utcnow(),
                "iss": "invoiceflow-auth",  # Issuer
                "aud": "invoiceflow-app",   # Audience
            })
            
            encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
            
            log_auth_event(
                "token_created",
                user_email=data.get("sub"),
                success=True,
                expires_at=expire.isoformat()
            )
            
            return encoded_jwt
            
        except Exception as e:
            log_error(e, "JWT token creation failed")
            raise AuthenticationError("Failed to create access token")
    
    def verify_token(self, token: str) -> TokenData:
        """Verify and decode JWT token."""
        try:
            payload = jwt.decode(
                token, 
                self.secret_key, 
                algorithms=[self.algorithm],
                audience="invoiceflow-app",
                issuer="invoiceflow-auth"
            )
            
            # Extract email from subject claim
            email: str = payload.get("sub")
            user_id: int = payload.get("user_id")
            
            if email is None:
                raise AuthenticationError("Token missing email claim")
            
            token_data = TokenData(email=email, user_id=user_id)
            
            log_auth_event(
                "token_verified",
                user_email=email,
                success=True
            )
            
            return token_data
            
        except JWTError as e:
            log_auth_event(
                "token_verification_failed",
                success=False,
                error=str(e)
            )
            if "expired" in str(e).lower():
                raise AuthenticationError("Token has expired")
            elif "signature" in str(e).lower():
                raise AuthenticationError("Invalid token signature")
            else:
                raise AuthenticationError("Invalid token")
        except Exception as e:
            log_error(e, "Token verification error")
            raise AuthenticationError("Token verification failed")
    
    def get_token_expiry_seconds(self) -> int:
        """Get token expiry time in seconds."""
        return self.expiration_minutes * 60


# Global JWT manager instance
jwt_manager = JWTManager()


def create_user_token(user: User) -> Dict[str, Any]:
    """Create JWT token for user."""
    token_data = {
        "sub": user.email,  # Subject (user identifier)
        "user_id": user.id,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
    }
    
    access_token = jwt_manager.create_access_token(token_data)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": jwt_manager.get_token_expiry_seconds(),
    }


async def get_current_user_from_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get current user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Extract token from credentials
        token = credentials.credentials
        
        # Verify token and get token data
        token_data = jwt_manager.verify_token(token)
        
        # Get user from database
        user = db.query(User).filter(User.email == token_data.email).first()
        if user is None:
            log_auth_event(
                "user_not_found",
                user_email=token_data.email,
                success=False
            )
            raise credentials_exception
        
        # Check if user is active
        if not user.is_active:
            log_auth_event(
                "inactive_user_access",
                user_email=user.email,
                success=False
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive"
            )
        
        return user
        
    except AuthenticationError as e:
        logger.warning(f"Authentication failed: {str(e)}")
        raise credentials_exception
    except HTTPException:
        raise
    except Exception as e:
        log_error(e, "Unexpected error during authentication")
        raise credentials_exception


async def get_current_active_user(
    current_user: User = Depends(get_current_user_from_token)
) -> User:
    """Get current active user (additional check)."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    return current_user


def create_access_token_for_user(user: User) -> Dict[str, Any]:
    """Create access token for a specific user."""
    return create_user_token(user) 