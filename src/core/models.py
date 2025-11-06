# src/domain/models.py
from pydantic import BaseModel, Field
from typing import Optional, Literal, List, Dict, Any
from datetime import datetime

class DocumentTable(BaseModel):
    """Represents a table extracted from a document with contextual information."""
    table_index: int                           # Order within document
    page_number: Optional[int] = None          # Page where table appears
    
    # Contextual information
    title: Optional[str] = None                # Table title/caption if found
    context_before: Optional[str] = None       # Text before table (for context)
    context_after: Optional[str] = None        # Text after table (for context)
    section_heading: Optional[str] = None      # Section/chapter heading
    
    # Table structure
    headers: Optional[List[str]] = None        # Column headers
    rows: List[List[str]]                      # Table data as rows
    row_count: int
    column_count: int
    
    # Advanced structure (for complex tables)
    merged_cells: Optional[List[Dict]] = None  # Information about merged cells
    multi_level_headers: Optional[List[List[str]]] = None  # For complex headers
    spans_multiple_pages: bool = False         # If table continues across pages
    
    # Data types and validation
    column_types: Optional[List[str]] = None   # Detected data types per column
    data_quality_score: Optional[float] = None # Data quality assessment (0-1)
    extraction_errors: Optional[List[str]] = None  # Any errors during extraction
    
    # Table content representations
    table_text: Optional[str] = None           # Flattened text
    table_html: Optional[str] = None           # HTML representation
    table_markdown: Optional[str] = None       # Markdown representation
    table_csv: Optional[str] = None            # CSV representation
    
    # Metadata
    table_type: Optional[str] = None           # Detected table type (financial, data, etc.)
    confidence_score: Optional[float] = None   # Extraction confidence (0-1)
    extraction_method: Optional[str] = None    # Method used (pymupdf, ocr, text_pattern)
    processing_time_ms: Optional[int] = None   # Time taken to extract this table
    
    # Large file handling metadata (for all document types)
    is_truncated: Optional[bool] = False       # Whether table data was truncated
    original_row_count: Optional[int] = None   # Original number of rows before truncation
    stored_row_count: Optional[int] = None     # Number of rows actually stored
    truncation_reason: Optional[str] = None    # Reason for truncation

class ExtractedData(BaseModel):
    """The structured data we get from a document."""
    full_text: str
    author: Optional[str] = None
    page_count: int = 1
    has_ocr_content: bool = False
    processing_method: Optional[Literal['text_extraction', 'ocr', 'hybrid', 'hybrid_with_ocr', 'html_extraction', 'error']] = None
    tables: List[DocumentTable] = []           # Extracted tables
    table_count: int = 0                       # Number of tables found
    # Optional fields that may be populated when retrieved from database
    id: Optional[int] = None
    filename: Optional[str] = None
    created_at: Optional[datetime] = None

class Document(BaseModel):
    """Internal representation of a document."""
    content: bytes
    filename: str