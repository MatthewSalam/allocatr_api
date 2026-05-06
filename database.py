import os
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError, DatabaseError
from dotenv import load_dotenv
import logging
import time
from fastapi import HTTPException 


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    logger.error("DATABASE_URL environment variable is not set!")
    raise ValueError(
        "DATABASE_URL not found in environment variables. "
        "Please set it in .env file."
    )
if not DATABASE_URL.strip():
    raise ValueError("DATABASE_URL is empty")

try:
    if DATABASE_URL.startswith("sqlite"):
        engine = create_engine(
            DATABASE_URL, 
            connect_args={"check_same_thread": False}
        )
        logger.info("Using SQLite database")
    else:
        # PostgreSQL configuration for Neon (Pooled Connection)
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,  # Test connection before using
            pool_recycle=3600,   # Recycle connections after 1 hour
            echo=False           # Set to True for SQL query debugging
        )
        logger.info("✓ Database engine created for PostgreSQL (Neon)")
except Exception as e:
    logger.error(f"✗ Failed to create database engine: {e}")
    logger.error(f"DATABASE_URL format: {DATABASE_URL[:30]}...")
    raise

except Exception as e:
    logger.error(f"✗ Failed to create database engine: {e}")
    logger.error(f"DATABASE_URL format: {DATABASE_URL[:30]}...")
    raise

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Dependency for database session with connection error handling"""
    db = SessionLocal()
    try:
        # Test connection before yielding
        db.execute(text("SELECT 1"))
        yield db
    except OperationalError as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Database Connection Failed",
                "message": "Unable to connect to database. Please check your internet connection.",
                "type": "connection_error"
            }
        )
    except Exception as e:
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()

def test_database_connection():
    try:
        # Attempt to connect and query
        start_time = time.time()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            response_time = (time.time() - start_time) * 1000
        
        return {
            "status": "connected",
            "response_time_ms": round(response_time, 2),
            "database_type": "PostgreSQL (Neon)" if "postgresql" in DATABASE_URL else "SQLite",
            "message": "Database connection successful"
        }
    except OperationalError as e:
        logger.error(f"Connection test failed (OperationalError): {e}")
        return {
            "status": "disconnected",
            "error": "Connection Error",
            "message": "Cannot reach database server. Check internet connection or Neon status.",
            "details": str(e),
            "type": "operational_error"
        }
    except DatabaseError as e:
        logger.error(f"Connection test failed (DatabaseError): {e}")
        return {
            "status": "error",
            "error": "Database Error",
            "message": "Database error occurred",
            "details": str(e),
            "type": "database_error"
        }
    except Exception as e:
        logger.error(f"Connection test failed (Unknown): {e}")
        return {
            "status": "error",
            "error": "Unknown Error",
            "message": "An unexpected error occurred",
            "details": str(e),
            "type": "unknown_error"
        }

def init_db():
    """Create database tables with connection error handling"""
    try:
        logger.info("Creating database tables...")
        
        # First test connection
        connection_status = test_database_connection()
        if connection_status["status"] != "connected":
            logger.error(f"✗ Cannot create tables: {connection_status['message']}")
            raise ConnectionError(connection_status["message"])
        
        # Create tables
        Base.metadata.create_all(bind=engine)
        logger.info("✓ Database tables created/verified successfully")
        
    except OperationalError as e:
        logger.error(f"✗ Network/Connection error: {e}")
        logger.error("Possible causes:")
        logger.error("  - No internet connection")
        logger.error("  - Neon database is down")
        logger.error("  - Incorrect DATABASE_URL")
        logger.error("  - Firewall blocking connection")
        raise
    except Exception as e:
        logger.error(f"✗ Failed to create tables: {e}")
        raise