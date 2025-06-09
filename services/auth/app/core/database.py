"""
Database configuration and connection management for InvoiceFlow Auth Service
Handles database connections with retry logic and health checks
"""
import time
import asyncio
from typing import Generator, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from app.core.config import settings
from app.core.logging import get_logger, log_error
from app.models.user import Base

logger = get_logger("auth.database")

class DatabaseManager:
    """Manages database connections and health checks."""
    
    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self._is_connected = False
        
    def initialize(self) -> bool:
        """Initialize database connection with retry logic."""
        max_retries = 5
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempting database connection (attempt {attempt + 1}/{max_retries})")
                
                # Create engine with connection pooling
                self.engine = create_engine(
                    str(settings.database_url),
                    echo=settings.db_echo,
                    poolclass=QueuePool,
                    pool_size=5,
                    max_overflow=10,
                    pool_pre_ping=True,  # Validate connections before use
                    pool_recycle=3600,   # Recycle connections every hour
                    connect_args={"connect_timeout": 10}
                )
                
                # Test connection
                with self.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                
                # Create session factory
                self.SessionLocal = sessionmaker(
                    autocommit=False,
                    autoflush=False,
                    bind=self.engine
                )
                
                # Create tables
                Base.metadata.create_all(bind=self.engine)
                
                self._is_connected = True
                logger.info("Database connection established successfully")
                return True
                
            except Exception as e:
                logger.error(f"Database connection attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    log_error(e, "Failed to establish database connection after all retries")
                    return False
        
        return False
    
    def get_session(self) -> Generator[Session, None, None]:
        """Get database session with automatic cleanup."""
        if not self._is_connected or not self.SessionLocal:
            raise RuntimeError("Database not initialized")
        
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            log_error(e, "Database session error")
            raise
        finally:
            session.close()
    
    async def health_check(self) -> dict:
        """Perform database health check."""
        health_status = {
            "status": "unhealthy",
            "database": "disconnected",
            "details": {},
        }
        
        try:
            if not self.engine:
                health_status["details"]["error"] = "Database engine not initialized"
                return health_status
            
            # Test connection with timeout
            start_time = time.time()
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.fetchone()
            
            connection_time = round((time.time() - start_time) * 1000, 2)
            
            # Test session creation
            with self.get_session() as session:
                session.execute(text("SELECT COUNT(*) FROM users"))
            
            health_status.update({
                "status": "healthy",
                "database": "connected",
                "details": {
                    "connection_time_ms": connection_time,
                    "pool_size": self.engine.pool.size(),
                    "checked_out_connections": self.engine.pool.checkedout(),
                    "pool_overflow": self.engine.pool.overflow(),
                }
            })
            
        except SQLAlchemyError as e:
            health_status["details"]["error"] = f"Database error: {str(e)}"
            logger.error(f"Database health check failed: {str(e)}")
        except Exception as e:
            health_status["details"]["error"] = f"Unexpected error: {str(e)}"
            log_error(e, "Database health check error")
        
        return health_status
    
    def close(self):
        """Close database connections."""
        if self.engine:
            self.engine.dispose()
            self._is_connected = False
            logger.info("Database connections closed")


# Global database manager instance
db_manager = DatabaseManager()


def get_db() -> Generator[Session, None, None]:
    """Dependency for getting database session."""
    yield from db_manager.get_session()


def init_db() -> bool:
    """Initialize database connection."""
    return db_manager.initialize()


async def check_db_health() -> dict:
    """Check database health status."""
    return await db_manager.health_check()


def close_db():
    """Close database connections."""
    db_manager.close() 