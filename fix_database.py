from database import engine, Base, SessionLocal
from models import Student, User, Receipt, Room, Allocation, QRCode, Clearance
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def recreate_database():
    """
    Drop all tables and recreate them
    ⚠️ WARNING: This deletes all data!
    """
    logger.info("="*60)
    logger.info("RECREATING DATABASE")
    logger.info("⚠️  This will DELETE all existing data!")
    logger.info("="*60)
    
    confirm = input("Type 'YES' to continue: ")
    if confirm != "YES":
        logger.info("Cancelled.")
        return
    
    try:
        # Drop all tables
        logger.info("Dropping all tables...")
        Base.metadata.drop_all(bind=engine)
        logger.info("✓ All tables dropped")
        
        # Create all tables with updated schema
        logger.info("Creating all tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("✓ All tables created")
        
        logger.info("="*60)
        logger.info("✓ DATABASE RECREATED SUCCESSFULLY")
        logger.info("="*60)
        logger.info("All tables now have the latest columns!")
        logger.info("You can now start your server: python main.py")
        
    except Exception as e:
        logger.error(f"✗ Error recreating database: {e}")
        raise

if __name__ == "__main__":
    recreate_database()