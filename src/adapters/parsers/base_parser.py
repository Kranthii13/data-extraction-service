# src/infrastructure/parsers/base_parser.py
"""
Base Parser Module

Provides abstract base parser class with common utilities and interface definitions.
All concrete parsers should inherit from BaseParser to ensure consistent behavior.
"""

from abc import ABC, abstractmethod
from typing import Tuple, List, Optional
import asyncio
from src.core.ports import IDocumentParser
from src.core.models import DocumentTable


class BaseParser(IDocumentParser, ABC):
    """
    Abstract base parser class providing common utilities and interface.
    
    All concrete parsers should inherit from this class to ensure:
    - Consistent interface implementation
    - Common utility methods
    - Standardized error handling
    - Async processing support
    """
    
    def __init__(self):
        """Initialize base parser."""
        self._encoding_cache = {}
    
    @abstractmethod
    def parse(self, content: bytes) -> Tuple[str, bool, str]:
        """
        Parse document content and extract text.
        
        Args:
            content: Document content as bytes
            
        Returns:
            Tuple of (extracted_text, used_ocr, processing_method)
        """
        pass
    
    @abstractmethod
    def count_pages(self, content: bytes) -> int:
        """
        Count pages in document.
        
        Args:
            content: Document content as bytes
            
        Returns:
            Number of pages
        """
        pass
    
    @abstractmethod
    def extract_tables(self, content: bytes) -> List[DocumentTable]:
        """
        Extract tables from document.
        
        Args:
            content: Document content as bytes
            
        Returns:
            List of DocumentTable objects
        """
        pass
    
    async def parse_async(self, content: bytes) -> Tuple[str, bool, str]:
        """
        Parse document asynchronously.
        
        Args:
            content: Document content as bytes
            
        Returns:
            Tuple of (extracted_text, used_ocr, processing_method)
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.parse, content)
    
    async def extract_tables_async(self, content: bytes) -> List[DocumentTable]:
        """
        Extract tables asynchronously.
        
        Args:
            content: Document content as bytes
            
        Returns:
            List of DocumentTable objects
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.extract_tables, content)
    
    def _create_table_text(self, headers: Optional[List[str]], rows: List[List[str]]) -> str:
        """
        Create searchable text representation of table.
        
        Args:
            headers: Table headers (if any)
            rows: Table data rows
            
        Returns:
            Searchable text representation
        """
        text = ""
        if headers:
            text += " | ".join(headers) + "\n"
        for row in rows:
            text += " | ".join(row) + "\n"
        return text
    
    def _validate_content(self, content: bytes) -> bool:
        """
        Validate document content.
        
        Args:
            content: Document content as bytes
            
        Returns:
            True if content is valid
        """
        if not content:
            return False
        
        # Check minimum size (avoid empty files)
        if len(content) < 10:
            return False
        
        return True
    
    def _get_file_signature(self, content: bytes) -> str:
        """
        Get file signature from content.
        
        Args:
            content: Document content as bytes
            
        Returns:
            File signature string
        """
        if not content:
            return ""
        
        # Check common file signatures
        if content.startswith(b'%PDF'):
            return 'pdf'
        elif content.startswith(b'PK\x03\x04') and b'word/' in content[:1000]:
            return 'docx'
        elif content.startswith(b'\xff\xfe') or content.startswith(b'\xfe\xff'):
            return 'utf16'
        elif content.startswith(b'\xef\xbb\xbf'):
            return 'utf8_bom'
        
        return 'unknown'