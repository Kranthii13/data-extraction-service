# src/infrastructure/repositories.py
import os
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, text, func

from src.core.repositories import IDocumentRepository
from src.core.models import Document, ExtractedData
from src.adapters.database.models import DocumentRecord

class SqlDocumentRepository(IDocumentRepository):
    """
    Enhanced SQLAlchemy implementation with PostgreSQL Full-Text Search.
    Supports OCR metadata and advanced search capabilities.
    """
    
    def __init__(self, db_session: Session):
        self.db = db_session
    
    def save_extracted_data(self, document: Document, extracted_data: ExtractedData) -> int:
        """Save document with compression and deduplication."""
        import hashlib
        import gzip
        
        # Calculate file hash for deduplication
        file_hash = hashlib.sha256(document.content).hexdigest()
        
        # Check for existing document
        existing = self.db.query(DocumentRecord).filter(
            DocumentRecord.file_hash == file_hash
        ).first()
        
        if existing:
            # Update existing document with new extraction results
            document_id = self._update_existing_document(existing, document, extracted_data)
            return {"id": document_id, "action": "updated"}
        
        # Get file extension and size
        _, file_ext = os.path.splitext(document.filename)
        file_size = len(document.content)
        
        # Skip compression for faster processing
        compressed_text = None
        
        # Create database record
        db_document = DocumentRecord(
            filename=document.filename,
            file_extension=file_ext.lower(),
            file_size=file_size,
            file_hash=file_hash,
            full_text=extracted_data.full_text,  # Complete extracted text
            full_text_compressed=compressed_text,  # Compressed version for storage efficiency
            page_count=extracted_data.page_count,
            word_count=len(extracted_data.full_text.split()),
            author=extracted_data.author,
            has_ocr_content=1 if extracted_data.has_ocr_content else 0,
            processing_method=extracted_data.processing_method,
            table_count=extracted_data.table_count
        )
        
        # Save to database
        self.db.add(db_document)
        self.db.flush()  # Get the document ID
        
        # Save tables as JSON if any
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"Checking for table data in extracted_data")
        logger.info(f"Has _raw_tables attribute: {hasattr(extracted_data, '_raw_tables')}")
        
        if hasattr(extracted_data, '_raw_tables'):
            logger.info(f"_raw_tables length: {len(extracted_data._raw_tables) if extracted_data._raw_tables else 0}")
            logger.info(f"_raw_tables type: {type(extracted_data._raw_tables)}")
            
            if extracted_data._raw_tables:
                logger.info(f"Saving {len(extracted_data._raw_tables)} tables to database")
                # Use the raw table data directly (already in dictionary format)
                db_document.tables_data = extracted_data._raw_tables
            else:
                logger.warning("_raw_tables is empty")
        else:
            logger.warning("No _raw_tables attribute found")
        
        self.db.commit()
        
        # Update the search vector using PostgreSQL's built-in FTS
        self._update_search_vector(db_document.id)
        
        self.db.refresh(db_document)
        return {"id": db_document.id, "action": "created"}
    
    def _update_search_vector(self, document_id: int):
        """Update the full-text search vector for a document."""
        update_query = text("""
            UPDATE documents 
            SET search_vector = to_tsvector('english', 
                coalesce(filename, '') || ' ' || 
                coalesce(full_text, '') || ' ' || 
                coalesce(author, '')
            )
            WHERE id = :doc_id
        """)
        self.db.execute(update_query, {"doc_id": document_id})
        self.db.commit()
    
    def get_by_id(self, document_id: int) -> Optional[ExtractedData]:
        """Get document by ID with tables."""
        db_document = self.db.query(DocumentRecord).filter(
            DocumentRecord.id == document_id
        ).first()
        
        if not db_document:
            return None
        
        return self._to_domain_model(db_document)
    
    def get_by_filename(self, filename: str) -> List[ExtractedData]:
        """Get all documents with the given filename."""
        db_documents = self.db.query(DocumentRecord).filter(
            DocumentRecord.filename == filename
        ).all()
        
        return [self._to_domain_model(doc) for doc in db_documents]
    
    def get_all(self, limit: int = 100, offset: int = 0) -> List[ExtractedData]:
        """Get all documents with pagination."""
        db_documents = self.db.query(DocumentRecord)\
            .order_by(DocumentRecord.created_at.desc())\
            .offset(offset)\
            .limit(limit)\
            .all()
        
        return [self._to_domain_model(doc) for doc in db_documents]
    
    def search_by_text(self, search_term: str, limit: int = 100) -> List[ExtractedData]:
        """
        Advanced search using PostgreSQL Full-Text Search.
        Supports phrase queries, boolean operators, and ranking.
        """
        # Prepare the search query for PostgreSQL FTS
        # Handle both simple terms and phrase queries
        if '"' in search_term:
            # Phrase search
            fts_query = search_term
        else:
            # Convert space-separated terms to AND query
            terms = search_term.strip().split()
            fts_query = ' & '.join(terms)
        
        # Use PostgreSQL's full-text search with ranking
        search_query = text("""
            SELECT *, ts_rank(search_vector, to_tsquery('english', :query)) as rank
            FROM documents 
            WHERE search_vector @@ to_tsquery('english', :query)
            ORDER BY rank DESC, created_at DESC
            LIMIT :limit
        """)
        
        try:
            result = self.db.execute(search_query, {
                "query": fts_query,
                "limit": limit
            })
            
            # Convert results to domain models
            documents = []
            for row in result:
                # Create a DocumentRecord-like object from the row
                db_document = DocumentRecord()
                for column in DocumentRecord.__table__.columns:
                    if hasattr(row, column.name):
                        setattr(db_document, column.name, getattr(row, column.name))
                
                documents.append(self._to_domain_model(db_document))
            
            return documents
            
        except Exception as e:
            print(f"FTS search failed, falling back to ILIKE: {e}")
            # Fallback to ILIKE search if FTS fails
            return self._fallback_search(search_term, limit)
    
    def _fallback_search(self, search_term: str, limit: int = 100) -> List[ExtractedData]:
        """Fallback search using ILIKE when FTS fails."""
        db_documents = self.db.query(DocumentRecord).filter(
            or_(
                DocumentRecord.full_text.ilike(f"%{search_term}%"),
                DocumentRecord.filename.ilike(f"%{search_term}%"),
                DocumentRecord.author.ilike(f"%{search_term}%")
            )
        ).order_by(DocumentRecord.created_at.desc()).limit(limit).all()
        
        return [self._to_domain_model(doc) for doc in db_documents]
    
    def search_by_processing_method(self, method: str, limit: int = 100) -> List[ExtractedData]:
        """Search documents by processing method (text_extraction, ocr, hybrid)."""
        db_documents = self.db.query(DocumentRecord).filter(
            DocumentRecord.processing_method == method
        ).order_by(DocumentRecord.created_at.desc()).limit(limit).all()
        
        return [self._to_domain_model(doc) for doc in db_documents]
    
    def get_ocr_documents(self, limit: int = 100) -> List[ExtractedData]:
        """Get all documents that used OCR processing."""
        db_documents = self.db.query(DocumentRecord).filter(
            DocumentRecord.has_ocr_content == 1
        ).order_by(DocumentRecord.created_at.desc()).limit(limit).all()
        
        return [self._to_domain_model(doc) for doc in db_documents]
    
    def _to_domain_model(self, db_document: DocumentRecord) -> ExtractedData:
        """Convert database model to domain model with tables from JSON."""
        from src.core.models import DocumentTable as DomainTable
        
        # Load tables from JSON
        tables = []
        if db_document.tables_data:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Loading {len(db_document.tables_data)} tables from database")
            
            for i, table_dict in enumerate(db_document.tables_data):
                try:
                    logger.info(f"Processing table {i}: {list(table_dict.keys())}")
                    
                    # Create DocumentTable with only the fields we have
                    domain_table = DomainTable(
                        table_index=table_dict.get("table_index", 0),
                        headers=table_dict.get("headers"),
                        rows=table_dict.get("rows", []),
                        row_count=table_dict.get("row_count", 0),
                        column_count=table_dict.get("column_count", 0),
                        # Optional fields
                        page_number=table_dict.get("page_number"),
                        title=table_dict.get("title"),
                        context_before=table_dict.get("context_before"),
                        context_after=table_dict.get("context_after"),
                        table_type=table_dict.get("table_type"),
                        confidence_score=table_dict.get("confidence_score"),
                        extraction_method=table_dict.get("extraction_method")
                    )
                    tables.append(domain_table)
                    logger.info(f"Successfully created DocumentTable {i}")
                    
                except Exception as e:
                    # Log the error but continue with other tables
                    logger.error(f"Failed to create DocumentTable {i} from dict: {e}")
                    logger.error(f"Table dict keys: {list(table_dict.keys()) if table_dict else 'None'}")
                    continue
            
            logger.info(f"Successfully loaded {len(tables)} tables")
        
        return ExtractedData(
            id=db_document.id,
            full_text=db_document.full_text,
            page_count=db_document.page_count,
            author=db_document.author,
            filename=db_document.filename,
            created_at=db_document.created_at,
            has_ocr_content=bool(db_document.has_ocr_content),
            processing_method=db_document.processing_method,
            tables=tables,
            table_count=db_document.table_count or 0
        )
    
    def _validate_table_data(self, table: 'DocumentTable') -> 'DocumentTable':
        """Validate and clean table data before storage."""
        from src.core.models import DocumentTable
        
        # Validate basic structure
        if not table.rows:
            raise ValueError("Table must have at least one row")
        
        # Ensure consistent row lengths
        max_columns = max(len(row) for row in table.rows) if table.rows else 0
        
        # Pad short rows with empty strings
        normalized_rows = []
        for row in table.rows:
            if len(row) < max_columns:
                padded_row = row + [""] * (max_columns - len(row))
                normalized_rows.append(padded_row)
            else:
                normalized_rows.append(row[:max_columns])  # Truncate if too long
        
        # Validate headers
        normalized_headers = table.headers
        if normalized_headers and len(normalized_headers) != max_columns:
            if len(normalized_headers) < max_columns:
                # Pad headers
                normalized_headers = normalized_headers + [f"Column_{i+1}" for i in range(len(normalized_headers), max_columns)]
            else:
                # Truncate headers
                normalized_headers = normalized_headers[:max_columns]
        
        # Clean text content (remove excessive whitespace, control characters)
        def clean_text(text: str) -> str:
            if not text:
                return ""
            # Remove control characters except newlines and tabs
            cleaned = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t')
            # Normalize whitespace
            return ' '.join(cleaned.split())
        
        # Clean all text content
        cleaned_rows = []
        for row in normalized_rows:
            cleaned_row = [clean_text(str(cell)) for cell in row]
            cleaned_rows.append(cleaned_row)
        
        if normalized_headers:
            normalized_headers = [clean_text(str(header)) for header in normalized_headers]
        
        # Create validated table with only required fields to avoid validation issues
        return DocumentTable(
            table_index=table.table_index,
            headers=normalized_headers,
            rows=cleaned_rows,
            row_count=len(cleaned_rows),
            column_count=max_columns,
            # Optional fields with safe defaults
            page_number=table.page_number,
            title=clean_text(table.title) if table.title else None,
            context_before=clean_text(table.context_before) if table.context_before else None,
            context_after=clean_text(table.context_after) if table.context_after else None,
            section_heading=clean_text(table.section_heading) if table.section_heading else None,
            table_type=table.table_type,
            confidence_score=table.confidence_score,
            extraction_method=table.extraction_method
        )
    
    def _update_existing_document(self, existing: DocumentRecord, document: Document, extracted_data: ExtractedData) -> int:
        """
        Update existing document with new extraction results.
        This allows re-processing documents with improved OCR or processing methods.
        
        Args:
            existing: Existing document record in database
            document: New document data
            extracted_data: New extraction results
            
        Returns:
            Document ID of updated record
        """
        import gzip
        from datetime import datetime
        
        # Update the existing record with new data
        existing.filename = document.filename  # Update filename in case it changed
        existing.full_text = extracted_data.full_text
        
        # Skip compression for faster processing
        existing.full_text_compressed = None
        
        # Update extraction metadata
        existing.page_count = extracted_data.page_count
        existing.word_count = len(extracted_data.full_text.split())
        existing.author = extracted_data.author
        existing.has_ocr_content = 1 if extracted_data.has_ocr_content else 0
        existing.processing_method = extracted_data.processing_method
        existing.table_count = extracted_data.table_count
        existing.updated_at = datetime.utcnow()
        
        # Update tables data - use _raw_tables like in the main save method
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"Updating document {existing.id} - checking for table data")
        logger.info(f"Has _raw_tables attribute: {hasattr(extracted_data, '_raw_tables')}")
        
        if hasattr(extracted_data, '_raw_tables') and extracted_data._raw_tables:
            logger.info(f"Updating with {len(extracted_data._raw_tables)} tables")
            # Use the raw table data directly (already in dictionary format)
            existing.tables_data = extracted_data._raw_tables
        else:
            logger.warning("No _raw_tables found in update, setting to None")
            existing.tables_data = None
        
        # Update search vector for full-text search
        if existing.full_text:
            try:
                from sqlalchemy import text
                update_search_vector = text("""
                    UPDATE documents 
                    SET search_vector = to_tsvector('english', :full_text)
                    WHERE id = :doc_id
                """)
                self.db.execute(update_search_vector, {
                    "full_text": existing.full_text,
                    "doc_id": existing.id
                })
            except Exception as e:
                print(f"Warning: Failed to update search vector: {e}")
        
        # Commit the update
        self.db.commit()
        
        print(f"Document updated with ID: {existing.id} (Method: {existing.processing_method}, OCR: {bool(existing.has_ocr_content)}, Tables: {existing.table_count})")
        
        return existing.id