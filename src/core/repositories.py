# src/domain/repositories.py
from abc import ABC, abstractmethod
from typing import List, Optional
from .models import Document, ExtractedData

class IDocumentRepository(ABC):
    """
    Domain repository interface for document persistence.
    This defines what operations we need without specifying how they're implemented.
    """
    
    @abstractmethod
    def save_extracted_data(self, document: Document, extracted_data: ExtractedData) -> int:
        """
        Save document and its extracted data to storage.
        Returns the ID of the saved record.
        """
        pass
    
    @abstractmethod
    def get_by_id(self, document_id: int) -> Optional[ExtractedData]:
        """Get extracted data by document ID."""
        pass
    
    @abstractmethod
    def get_by_filename(self, filename: str) -> List[ExtractedData]:
        """Get all documents with the given filename."""
        pass
    
    @abstractmethod
    def get_all(self, limit: int = 100, offset: int = 0) -> List[ExtractedData]:
        """Get all documents with pagination."""
        pass
    
    @abstractmethod
    def search_by_text(self, search_term: str, limit: int = 100) -> List[ExtractedData]:
        """Search documents by text content using PostgreSQL FTS."""
        pass
    
    @abstractmethod
    def search_by_processing_method(self, method: str, limit: int = 100) -> List[ExtractedData]:
        """Search documents by processing method (text_extraction, ocr, hybrid)."""
        pass
    
    @abstractmethod
    def get_ocr_documents(self, limit: int = 100) -> List[ExtractedData]:
        """Get all documents that used OCR processing."""
        pass