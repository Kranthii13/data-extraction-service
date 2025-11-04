# src/application/ports.py
from abc import ABC, abstractmethod
from typing import Optional
from src.core.models import Document, ExtractedData

class IExtractionService(ABC):
    """
    The main entry point for the application's logic.
    This is the interface the API (or CLI) will call.
    """
    @abstractmethod
    def extract_from_document(self, doc: Document) -> ExtractedData:
        pass
    
    @abstractmethod
    def get_document_by_id(self, document_id: int) -> Optional[ExtractedData]:
        pass
    
    @abstractmethod
    def search_documents(self, search_term: str, limit: int = 100) -> list[ExtractedData]:
        pass
    
    @abstractmethod
    def get_all_documents(self, limit: int = 100, offset: int = 0) -> list[ExtractedData]:
        pass
    
    @abstractmethod
    def get_documents_by_processing_method(self, method: str, limit: int = 100) -> list[ExtractedData]:
        pass
    
    @abstractmethod
    def get_ocr_documents(self, limit: int = 100) -> list[ExtractedData]:
        pass