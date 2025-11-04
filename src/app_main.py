#!/usr/bin/env python3
"""
Main Application Entry Point
Data Extraction Service with Clean Architecture
"""

import os
import sys
import logging
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def setup_logging():
    """Configure application logging"""
    from src.config.app_config import config
    
    log_level = getattr(logging, config.app.log_level.upper(), logging.INFO)
    
    handlers = [logging.StreamHandler(sys.stdout)]
    if config.app.log_to_file:
        handlers.append(logging.FileHandler('app.log'))
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
    
    # Set specific logger levels
    logging.getLogger('src.services.table_extraction_service').setLevel(logging.INFO)
    logging.getLogger('src.adapters.parsers.pdf_parser').setLevel(logging.INFO)

def check_environment():
    """Verify required environment variables"""
    from src.config.app_config import config
    
    logger = logging.getLogger(__name__)
    
    # Check database configuration
    required_vars = ['POSTGRES_HOST', 'POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        sys.exit(1)
    
    logger.info("Environment validation completed")
    logger.info(f"Database: {config.database.host}:{config.database.port}/{config.database.database}")
    logger.info(f"OCR enabled: {config.ocr.enabled}")
    logger.info(f"Table extraction enabled: {config.table_extraction.enabled}")

def initialize_application():
    """Initialize application components"""
    logger = logging.getLogger(__name__)
    
    try:
        # Import here to ensure environment is set up first
        from src.adapters.dependencies import engine
        
        # Test database connection
        with engine.connect() as conn:
            logger.info("Database connection established")
        
        logger.info("Application initialization completed")
        return True
        
    except Exception as e:
        logger.error(f"Application initialization failed: {e}")
        return False

def start_server():
    """Start the FastAPI server"""
    from src.config.app_config import config
    import uvicorn
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting Data Extraction Service on {config.app.host}:{config.app.port}")
    
    try:
        uvicorn.run(
            "src.adapters.api:app",
            host=config.app.host,
            port=config.app.port,
            reload=config.app.reload,
            log_level=config.app.log_level,
            access_log=True
        )
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)

def main():
    """Main application entry point"""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 Starting Data Extraction Service...")
    logger.info("=" * 50)
    
    # Validate environment
    check_environment()
    
    # Initialize application
    if not initialize_application():
        logger.error("Failed to initialize application. Exiting.")
        sys.exit(1)
    
    # Start the server
    start_server()

if __name__ == "__main__":
    main()