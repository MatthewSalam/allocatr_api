from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db, test_database_connection
import logging
from api.endpoints import auth
from api.endpoints import admin
from api.endpoints import clearance
from api.endpoints import receipts
from api.endpoints import students

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Hostel Allocation & QR Clearance System",
    version="1.0.0"
)

# CORS - Allow frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production: ["https://yourfrontend.com"]
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