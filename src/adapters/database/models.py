# src/infrastructure/database/models.py
from sqlalchemy import Column, Integer, String, Text, DateTime, LargeBinary, Index, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import TSVECTOR
from datetime import datetime

Base = declarative_base()

class DocumentRecord(Base):
    """
    SQLAlchemy model for storing document metadata and extracted data.
    Enhanced with PostgreSQL Full-Text Search capabilities.
    """
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False, index=True)
    file_extension = Column(String(10), nullable=False)
    file_size = Column(Integer, nullable=False)  # Size in bytes
    
    # Extracted content (compressed for efficiency)
    full_text_compressed = Column(LargeBinary, nullable=True)  # gzip compressed text
    full_text = Column(Text, nullable=False)  # Complete extracted text
    page_count = Column(Integer, default=1)
    word_count = Column(Integer, default=0)
    author = Column(String(255), nullable=True)
    file_hash = Column(String(64), nullable=True, index=True)  # For deduplication
    
    # OCR and processing metadata
    has_ocr_content = Column(Integer, default=0)  # Boolean: 1 if OCR was used
    processing_method = Column(String(50), nullable=True)  # 'text_extraction', 'ocr', 'hybrid'
    
    # Full-text search vector (automatically maintained by PostgreSQL)
    search_vector = Column(TSVECTOR)
    
    # Table extraction data stored as JSON
    tables_data = Column(JSON, nullable=True)     # All extracted tables as JSON
    table_count = Column(Integer, default=0)      # Number of tables found
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<DocumentRecord(id={self.id}, filename='{self.filename}', pages={self.page_count}, tables={self.table_count})>"

# Create indexes for performance
Index('ix_documents_search_vector', DocumentRecord.search_vector, postgresql_using='gin')
Index('ix_documents_table_count', DocumentRecord.table_count)