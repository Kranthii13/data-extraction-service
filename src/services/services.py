# src/application/services.py
from src.core.models import Document, ExtractedData, DocumentTable
from typing import List
from src.core.ports import IDocumentParser
from src.core.repositories import IDocumentRepository
from src.services.ports import IExtractionService
from typing import Dict, Optional
import os
import logging

logger = logging.getLogger(__name__)

class ExtractionService(IExtractionService):
    """
    This is the core application logic.
    It implements the IExtractionService interface.
    It depends on the IDocumentParser interface and IDocumentRepository.
    """
    
    def __init__(self, parser_map: Dict[str, IDocumentParser], repository: IDocumentRepository):
        self._parser_map = parser_map
        self._repository = repository

    def _get_parser(self, file_extension: str) -> IDocumentParser:
        """
        Selects the correct parser based on the file extension.
        Falls back to generic text parser for unknown extensions.
        """
        parser = self._parser_map.get(file_extension)
        if not parser:
            # Import here to avoid circular imports
            from src.adapters.parsers.generic_text_parser import GenericTextParser
            # Fall back to generic text parser for unknown file types
            return GenericTextParser()
        return parser

    def extract_from_document(self, doc: Document) -> ExtractedData:
        """
        Orchestrates the extraction process and saves to database.
        Supports any text-based file format with intelligent fallback parsing.
        """
        _, file_ext = os.path.splitext(doc.filename)
        file_ext = file_ext.lower()
        
        # Handle files without extensions
        if not file_ext:
            file_ext = self._detect_file_type(doc.filename, doc.content)
        
        try:
            # 1. Get the parser (with fallback to generic parser)
            parser = self._get_parser(file_ext)
            
            # 2. Use the parser to extract content and tables
            full_text, used_ocr, processing_method = parser.parse(doc.content)
            page_count = parser.count_pages(doc.content)
            
            # 3. Extract tables with comprehensive error handling
            tables = []
            table_extraction_errors = []
            
            try:
                # Extract tables for supported file types
                if file_ext in ['.pdf', '.docx', '.doc', '.html', '.htm'] and len(doc.content) < 10 * 1024 * 1024:  # Files < 10MB
                    logger.info(f"Extracting tables from {doc.filename} ({file_ext})")
                    raw_tables = parser.extract_tables(doc.content)
                    
                    # Apply size limits to prevent browser crashes (for all document types)
                    limited_tables = self._limit_table_sizes(raw_tables)
                    
                    # Convert tables to simple dictionaries to avoid validation issues
                    tables = []
                    for table in limited_tables:
                        if table.row_count > 0 and table.column_count > 0:
                            # Create a simple dictionary representation
                            table_dict = {
                                "table_index": table.table_index,
                                "headers": table.headers,
                                "rows": table.rows,
                                "row_count": table.row_count,
                                "column_count": table.column_count,
                                "page_number": table.page_number,
                                "title": table.title,
                                "context_before": table.context_before,
                                "context_after": table.context_after,
                                "table_type": table.table_type,
                                "confidence_score": table.confidence_score,
                                "extraction_method": table.extraction_method,
                                # Add truncation metadata for all document types
                                "is_truncated": getattr(table, 'is_truncated', False),
                                "original_row_count": getattr(table, 'original_row_count', table.row_count),
                                "stored_row_count": getattr(table, 'stored_row_count', table.row_count),
                                "truncation_reason": getattr(table, 'truncation_reason', None)
                            }
                            tables.append(table_dict)
                        else:
                            logger.debug(f"Skipping empty table: {table.table_index}")
                    
                    logger.info(f"Found {len(tables)} valid tables in {doc.filename} (size limits applied to prevent browser crashes)")
                else:
                    tables = []  # Skip table extraction for large files or unsupported types
                    logger.debug(f"Skipping table extraction for {doc.filename}: file_ext={file_ext}, size={len(doc.content)}")
                
            except Exception as e:
                logger.debug(f"Table extraction failed for {doc.filename}: {e}")
                tables = []  # Continue without tables

            # 4. Sanitize text to prevent database errors
            sanitized_text = self._sanitize_text_for_database(full_text)
            
            # 5. Create the domain model with metadata
            extracted_data = ExtractedData(
                full_text=sanitized_text,
                page_count=page_count,
                has_ocr_content=1 if used_ocr else 0,  # Convert boolean to integer
                processing_method=processing_method,
                tables=[],  # We'll store tables as raw data in the database
                table_count=len(tables)
            )
            
            # Store raw table data for database storage
            extracted_data._raw_tables = tables
            
            # 5. Save to database using repository
            save_result = self._repository.save_extracted_data(doc, extracted_data)
            document_id = save_result["id"]
            action = save_result["action"]
            
            action_text = "updated" if action == "updated" else "saved"
            print(f"Document {action_text} with ID: {document_id} (Type: {file_ext or 'unknown'}, Method: {processing_method}, OCR: {used_ocr}, Tables: {len(tables)})")
            
            # 6. Add document ID and filename to the response
            extracted_data.id = document_id
            extracted_data.filename = doc.filename
            
            # 7. Return the domain model
            return extracted_data
            
        except Exception as e:
            logger.error(f"Error extracting data from {doc.filename}: {e}")
            
            # Return a minimal result instead of failing completely
            return ExtractedData(
                full_text=f"Error processing document: {str(e)}",
                page_count=1,
                has_ocr_content=0,  # Convert boolean False to integer 0
                processing_method="error",
                tables=[],
                table_count=0
            )
    
    def _sanitize_text_for_database(self, text: str) -> str:
        """
        Fast text sanitization for database storage
        """
        if not text:
            return ""
        
        # Quick NUL character removal
        sanitized = text.replace('\x00', '')
        
        # Limit text length for faster processing (500KB max)
        max_length = 512 * 1024  # 512KB
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length] + "\n[Text truncated]"
        
        return sanitized
    
    def _limit_table_sizes(self, tables: List[DocumentTable]) -> List[DocumentTable]:
        """
        Apply size limits to all tables to prevent browser crashes.
        Works for tables from any document type (PDF, DOCX, HTML, etc.)
        """
        from src.config.app_config import config
        
        if not tables:
            return tables
        
        limited_tables = []
        max_rows = config.large_file.max_storage_rows
        
        for table in tables:
            # Create a copy of the table to avoid modifying the original
            table_dict = table.dict()
            
            # Limit the rows if they exist and are too large
            if table_dict.get('rows') and len(table_dict['rows']) > max_rows:
                original_count = len(table_dict['rows'])
                table_dict['rows'] = table_dict['rows'][:max_rows]
                
                # Add truncation metadata
                table_dict['is_truncated'] = True
                table_dict['original_row_count'] = original_count
                table_dict['stored_row_count'] = len(table_dict['rows'])
                table_dict['truncation_reason'] = 'Large table truncated to prevent browser crashes'
                
                logger.warning(f"Table {table.table_index} truncated: {original_count} → {max_rows} rows")
            else:
                table_dict['is_truncated'] = False
                table_dict['original_row_count'] = len(table_dict.get('rows', []))
                table_dict['stored_row_count'] = len(table_dict.get('rows', []))
            
            # Create new DocumentTable with limited data
            try:
                limited_table = DocumentTable(**table_dict)
                limited_tables.append(limited_table)
            except Exception as e:
                logger.error(f"Failed to create limited table: {e}")
                # If creation fails, use original table
                limited_tables.append(table)
        
        return limited_tables
    
    def _detect_file_type(self, filename: str, content: bytes) -> str:
        """
        Attempt to detect file type for files without extensions.
        
        Args:
            filename: Name of the file
            content: File content bytes
            
        Returns:
            str: Detected file extension or empty string for generic parsing
        """
        filename_lower = filename.lower()
        
        # Common files without extensions
        if filename_lower in ['readme', 'license', 'changelog', 'authors', 'contributors', 'makefile', 'dockerfile']:
            return f".{filename_lower}"
        
        # Try to detect based on content
        try:
            # Check first few bytes for common signatures
            if content.startswith(b'%PDF'):
                return '.pdf'
            elif content.startswith(b'PK\x03\x04') and b'word/' in content[:1000]:
                return '.docx'
            elif content.startswith(b'{\n') or content.startswith(b'[\n'):
                return '.json'
            elif content.startswith(b'<'):
                return '.xml'
        except:
            pass
        
        # Default to generic text parsing
        return ''

    def get_document_by_id(self, document_id: int) -> Optional[ExtractedData]:
        """Retrieve a document by its ID."""
        return self._repository.get_by_id(document_id)
    
    def search_documents(self, search_term: str, limit: int = 100) -> list[ExtractedData]:
        """Search documents by text content."""
        return self._repository.search_by_text(search_term, limit)
    
    def get_all_documents(self, limit: int = 100, offset: int = 0) -> list[ExtractedData]:
        """Get all documents with pagination."""
        return self._repository.get_all(limit, offset)
    
    def get_documents_by_processing_method(self, method: str, limit: int = 100) -> list[ExtractedData]:
        """Get documents by processing method."""
        return self._repository.search_by_processing_method(method, limit)
    
    def get_ocr_documents(self, limit: int = 100) -> list[ExtractedData]:
        """Get all documents that used OCR."""
        return self._repository.get_ocr_documents(limit)