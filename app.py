from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db, test_database_connection
import logging
from api.endpoints import auth, admin, clearance, receipts, students
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Hostel Allocation & QR Clearance System",
    version="1.0.0"
)

origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    """Run when app starts"""
    logger.info("="*60)
    logger.info("Starting Hostel System...")
    logger.info("="*60)
    
    # Test database connection
    db_status = test_database_connection()
    if db_status["status"] == "connected":
        logger.info("✓ Database connected")
        init_db()
    else:
        logger.error("✗ Database connection failed")

@app.get("/")
def root():
    return {
        "message": "Hostel Allocation & QR Clearance System API",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running"
    }

@app.get("/health")
def health():
    return {"status": "healthy"}

app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(clearance.router)
app.include_router(receipts.router)
app.include_router(students.router) 