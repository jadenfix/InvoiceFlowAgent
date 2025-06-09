"""
Authentication API routes for InvoiceFlow Auth Service
Handles user registration, login, and authentication endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
from app.core.database import get_db
from app.core.auth import create_user_token, get_current_active_user
from app.core.rate_limiter import (
    check_rate_limit, record_failed_attempt, record_successful_login,
    check_user_account_lockout
)
from app.core.logging import get_logger, log_auth_event, log_error
from app.models.user import User, UserCreate, UserLogin, UserResponse, Token

logger = get_logger("auth.api")
router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Register a new user with comprehensive validation and error handling.
    
    Validates:
    - Email format and uniqueness
    - Password strength requirements
    - Input sanitization
    
    Returns:
    - User profile (without password)
    - HTTP 201 on success
    - HTTP 400 on validation errors
    - HTTP 409 on duplicate email
    - HTTP 429 on rate limit exceeded
    """
    try:
        # Check rate limits
        check_rate_limit(request, user_data.email)
        
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == user_data.email).first()
        if existing_user:
            log_auth_event(
                "registration_failed_duplicate_email",
                user_email=user_data.email,
                success=False
            )
            # Still record as failed attempt to prevent enumeration
            record_failed_attempt(request, user_data.email)
            
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "Registration failed",
                    "message": "An account with this email already exists",
                    "field": "email"
                }
            )
        
        # Create new user
        user = User(
            email=user_data.email,
            full_name=user_data.full_name,
        )
        user.set_password(user_data.password)
        
        # Save to database
        db.add(user)
        db.commit()
        db.refresh(user)
        
        log_auth_event(
            "user_registered",
            user_email=user.email,
            success=True,
            user_id=user.id
        )
        
        logger.info(f"New user registered successfully: {user.email}")
        
        return UserResponse.from_orm(user)
        
    except HTTPException:
        # Re-raise HTTP exceptions (rate limits, duplicates, etc.)
        raise
    except ValidationError as e:
        # Handle Pydantic validation errors
        log_auth_event(
            "registration_failed_validation",
            user_email=getattr(user_data, 'email', 'unknown'),
            success=False,
            validation_errors=str(e)
        )
        record_failed_attempt(request, getattr(user_data, 'email', None))
        
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "Validation failed",
                "message": "Invalid input data",
                "details": e.errors()
            }
        )
    except IntegrityError as e:
        # Handle database integrity errors
        db.rollback()
        log_error(e, "Database integrity error during registration")
        record_failed_attempt(request, user_data.email)
        
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "Registration failed",
                "message": "An account with this email already exists"
            }
        )
    except Exception as e:
        # Handle unexpected errors
        db.rollback()
        log_error(e, "Unexpected error during user registration")
        record_failed_attempt(request, getattr(user_data, 'email', None))
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal server error",
                "message": "Registration failed due to an internal error"
            }
        )


@router.post("/login", response_model=Token)
async def login_user(
    login_data: UserLogin,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Authenticate user and return JWT token.
    
    Validates:
    - Email and password format
    - User credentials
    - Account status and lockout
    - Rate limiting
    
    Returns:
    - JWT access token on success
    - HTTP 200 on success
    - HTTP 400 on validation errors
    - HTTP 401 on invalid credentials
    - HTTP 423 on account lockout
    - HTTP 429 on rate limit exceeded
    """
    try:
        # Check rate limits first
        check_rate_limit(request, login_data.email)
        
        # Get user from database
        user = db.query(User).filter(User.email == login_data.email).first()
        
        # Verify user exists and credentials are correct
        if not user or not user.verify_password(login_data.password):
            # Record failed attempt
            record_failed_attempt(request, login_data.email)
            
            # Update user's failed attempts if user exists
            if user:
                user.increment_failed_attempts()
                db.commit()
            
            log_auth_event(
                "login_failed_invalid_credentials",
                user_email=login_data.email,
                success=False
            )
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "Authentication failed",
                    "message": "Invalid email or password"
                }
            )
        
        # Check if account is locked
        check_user_account_lockout(user)
        
        # Check if user account is active
        if not user.is_active:
            log_auth_event(
                "login_failed_inactive_account",
                user_email=user.email,
                success=False
            )
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "Account disabled",
                    "message": "Your account has been disabled. Please contact support."
                }
            )
        
        # Reset failed attempts on successful login
        user.reset_failed_attempts()
        db.commit()
        
        # Record successful login
        record_successful_login(request, user.email)
        
        # Create JWT token
        token_data = create_user_token(user)
        
        log_auth_event(
            "login_successful",
            user_email=user.email,
            success=True,
            user_id=user.id
        )
        
        logger.info(f"User logged in successfully: {user.email}")
        
        return Token(**token_data)
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except ValidationError as e:
        # Handle validation errors
        log_auth_event(
            "login_failed_validation",
            user_email=getattr(login_data, 'email', 'unknown'),
            success=False,
            validation_errors=str(e)
        )
        record_failed_attempt(request, getattr(login_data, 'email', None))
        
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "Validation failed",
                "message": "Invalid input data",
                "details": e.errors()
            }
        )
    except Exception as e:
        # Handle unexpected errors
        db.rollback()
        log_error(e, "Unexpected error during user login")
        record_failed_attempt(request, getattr(login_data, 'email', None))
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal server error",
                "message": "Login failed due to an internal error"
            }
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    current_user: User = Depends(get_current_active_user)
):
    """
    Get current authenticated user profile.
    
    Requires:
    - Valid JWT token in Authorization header
    
    Returns:
    - Current user profile
    - HTTP 200 on success
    - HTTP 401 on invalid/missing token
    - HTTP 403 on inactive account
    """
    try:
        log_auth_event(
            "profile_accessed",
            user_email=current_user.email,
            success=True,
            user_id=current_user.id
        )
        
        return UserResponse.from_orm(current_user)
        
    except Exception as e:
        log_error(e, "Error retrieving user profile")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal server error",
                "message": "Failed to retrieve user profile"
            }
        )


@router.post("/logout")
async def logout_user(
    request: Request,
    current_user: User = Depends(get_current_active_user)
):
    """
    Logout current user.
    
    Note: With JWT tokens, actual logout requires client-side token deletion.
    This endpoint is for logging the logout event and any server-side cleanup.
    
    Returns:
    - Success message
    - HTTP 200 on success
    """
    try:
        log_auth_event(
            "user_logout",
            user_email=current_user.email,
            success=True,
            user_id=current_user.id
        )
        
        return {
            "message": "Logout successful",
            "detail": "Please remove the token from client storage"
        }
        
    except Exception as e:
        log_error(e, "Error during user logout")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal server error",
                "message": "Logout failed due to an internal error"
            }
        )


@router.get("/status")
async def get_auth_status():
    """
    Get authentication service status.
    
    Returns:
    - Service status and configuration info
    - HTTP 200 always
    """
    try:
        from app.core.config import settings
        
        return {
            "service": "InvoiceFlow Auth Service",
            "status": "operational",
            "version": "1.0.0",
            "environment": settings.environment,
            "features": {
                "registration": True,
                "login": True,
                "jwt_authentication": True,
                "rate_limiting": True,
                "account_lockout": True,
            },
            "security": {
                "password_min_length": settings.password_min_length,
                "jwt_expiration_minutes": settings.jwt_expiration_minutes,
                "rate_limit_attempts": settings.rate_limit_attempts,
                "rate_limit_window_minutes": settings.rate_limit_window_minutes,
            }
        }
        
    except Exception as e:
        log_error(e, "Error retrieving auth status")
        return {
            "service": "InvoiceFlow Auth Service",
            "status": "error",
            "message": "Failed to retrieve complete status"
        } 