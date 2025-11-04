# src/domain/ports.py
from abc import ABC, abstractmethod
from typing import Tuple, List
from src.core.models import DocumentTable

class IDocumentParser(ABC):
    """
    A port for any adapter that can parse a document's content.
    Enhanced to support OCR and processing method tracking.
    """
    @abstractmethod
    def parse(self, content: bytes) -> Tuple[str, bool, str]:
        """
        Parses document content and returns extraction details.
        
        Returns:
            Tuple of (extracted_text, used_ocr, processing_method)
        """
        pass

    @abstractmethod
    def count_pages(self, content: bytes) -> int:
        """Counts the pages in a document."""
        pass
    
    def extract_tables(self, content: bytes) -> List[DocumentTable]:
        """
        Extracts tables from document content.
        
        Returns:
            List of DocumentTable objects with structured table data
        """
        return []  # Default implementation returns no tables