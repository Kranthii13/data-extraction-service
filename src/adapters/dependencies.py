# src/infrastructure/dependencies.py
"""
Dependency injection configuration for the data extraction service.

This module sets up database connections, initializes services,
and configures the dependency injection container for the application.

Key responsibilities:
- Database connection management
- Service initialization and wiring
- Environment variable validation
- Full-text search setup
"""

import os
import logging
from typing import Dict, Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from src.core.ports import IDocumentParser
from src.core.repositories import IDocumentRepository
from src.services.ports import IExtractionService
from src.services.services import ExtractionService
from src.adapters.parsers.pdf_parser import PdfParser
from src.adapters.parsers.docx_parser import DocxParser
from src.adapters.parsers.generic_text_parser import GenericTextParser
from src.adapters.parsers.html_parser import HtmlParser
from src.adapters.repositories import SqlDocumentRepository
from src.adapters.database.models import Base, DocumentRecord

# Load environment variables
load_dotenv()

# Database configuration
DB_HOST = os.getenv("POSTGRES_HOST")
DB_PORT = os.getenv("POSTGRES_PORT")
DB_NAME = os.getenv("POSTGRES_DB")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")

# Validate required environment variables
if not all([DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD]):
    raise EnvironmentError("Database environment variables are not fully set!")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Database setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create database tables
logging.info("Initializing database tables...")
Base.metadata.create_all(bind=engine)

# Initialize PostgreSQL Full-Text Search
try:
    from src.adapters.database.init_fts import initialize_fts, update_existing_search_vectors
    db_session = SessionLocal()
    
    initialize_fts(db_session)
    update_existing_search_vectors(db_session)
    db_session.close()
    logging.info("Database and FTS initialization completed successfully")
except Exception as e:
    logging.warning(f"FTS initialization failed: {e}")
    logging.info("Database initialization completed successfully (without FTS)")



def get_db() -> Generator[Session, None, None]:
    """
    Database session dependency for FastAPI.
    
    Yields:
        Session: SQLAlchemy database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_document_repository(db: Session = None) -> IDocumentRepository:
    """
    Create document repository instance with database session.
    
    Args:
        db (Session, optional): Database session. If None, a new session will be created.
        
    Returns:
        IDocumentRepository: Document repository instance
    """
    if db is None:
        db = next(get_db())
    return SqlDocumentRepository(db)

def get_parser_map() -> Dict[str, IDocumentParser]:
    """
    Create and return a mapping of file extensions to their respective parsers.
    Supports a wide variety of text-based file formats including programming languages,
    markup files, configuration files, and documentation formats.
    
    Returns:
        Dict[str, IDocumentParser]: Mapping of file extensions to parser instances
    """
    # Create parser instances
    pdf_parser = PdfParser()
    docx_parser = DocxParser()
    generic_parser = GenericTextParser()
    html_parser = HtmlParser()
    
    return {
        # Document formats
        ".pdf": pdf_parser,
        ".docx": docx_parser,
        ".doc": html_parser,  # Many .doc files are actually HTML exports
        ".html": html_parser,
        ".htm": html_parser,
        ".txt": generic_parser,
        ".rtf": generic_parser,
        
        # Programming languages
        ".py": generic_parser,      # Python
        ".js": generic_parser,      # JavaScript
        ".ts": generic_parser,      # TypeScript
        ".jsx": generic_parser,     # React JSX
        ".tsx": generic_parser,     # React TSX
        ".java": generic_parser,    # Java
        ".c": generic_parser,       # C
        ".cpp": generic_parser,     # C++
        ".cc": generic_parser,      # C++
        ".cxx": generic_parser,     # C++
        ".h": generic_parser,       # C/C++ Header
        ".hpp": generic_parser,     # C++ Header
        ".cs": generic_parser,      # C#
        ".php": generic_parser,     # PHP
        ".rb": generic_parser,      # Ruby
        ".go": generic_parser,      # Go
        ".rs": generic_parser,      # Rust
        ".swift": generic_parser,   # Swift
        ".kt": generic_parser,      # Kotlin
        ".scala": generic_parser,   # Scala
        ".r": generic_parser,       # R
        ".m": generic_parser,       # Objective-C/MATLAB
        ".pl": generic_parser,      # Perl
        ".sh": generic_parser,      # Shell script
        ".bash": generic_parser,    # Bash script
        ".zsh": generic_parser,     # Zsh script
        ".fish": generic_parser,    # Fish script
        ".ps1": generic_parser,     # PowerShell
        ".bat": generic_parser,     # Batch file
        ".cmd": generic_parser,     # Command file
        
        # Web technologies
        ".html": generic_parser,    # HTML
        ".htm": generic_parser,     # HTML
        ".css": generic_parser,     # CSS
        ".scss": generic_parser,    # SASS
        ".sass": generic_parser,    # SASS
        ".less": generic_parser,    # LESS
        ".vue": generic_parser,     # Vue.js
        ".svelte": generic_parser,  # Svelte
        
        # Markup and documentation
        ".md": generic_parser,      # Markdown
        ".markdown": generic_parser, # Markdown
        ".rst": generic_parser,     # reStructuredText
        ".tex": generic_parser,     # LaTeX
        ".org": generic_parser,     # Org mode
        ".adoc": generic_parser,    # AsciiDoc
        ".asciidoc": generic_parser, # AsciiDoc
        
        # Configuration files
        ".json": generic_parser,    # JSON
        ".yaml": generic_parser,    # YAML
        ".yml": generic_parser,     # YAML
        ".toml": generic_parser,    # TOML
        ".ini": generic_parser,     # INI
        ".cfg": generic_parser,     # Config
        ".conf": generic_parser,    # Config
        ".config": generic_parser,  # Config
        ".xml": generic_parser,     # XML
        ".plist": generic_parser,   # Property List
        ".properties": generic_parser, # Properties
        ".env": generic_parser,     # Environment
        ".gitignore": generic_parser, # Git ignore
        ".gitattributes": generic_parser, # Git attributes
        ".dockerignore": generic_parser, # Docker ignore
        
        # Data formats
        ".csv": generic_parser,     # CSV
        ".tsv": generic_parser,     # TSV
        ".sql": generic_parser,     # SQL
        ".graphql": generic_parser, # GraphQL
        ".gql": generic_parser,     # GraphQL
        
        # Build and project files
        ".dockerfile": generic_parser, # Dockerfile
        ".makefile": generic_parser,   # Makefile
        ".cmake": generic_parser,      # CMake
        ".gradle": generic_parser,     # Gradle
        ".maven": generic_parser,      # Maven
        ".sbt": generic_parser,        # SBT
        ".package": generic_parser,    # Package files
        ".lock": generic_parser,       # Lock files
        
        # Log and text files
        ".log": generic_parser,     # Log files
        ".out": generic_parser,     # Output files
        ".err": generic_parser,     # Error files
        ".trace": generic_parser,   # Trace files
        
        # License and readme files (often without extensions)
        ".license": generic_parser,
        ".readme": generic_parser,
        ".changelog": generic_parser,
        ".authors": generic_parser,
        ".contributors": generic_parser,
    }

def get_extraction_service(db: Session = None) -> IExtractionService:
    """
    Create and configure the main extraction service with all dependencies.
    
    Args:
        db (Session, optional): Database session. If None, a new session will be created.
        
    Returns:
        IExtractionService: Configured extraction service instance
    """
    repository = get_document_repository(db)
    return ExtractionService(parser_map=get_parser_map(), repository=repository)