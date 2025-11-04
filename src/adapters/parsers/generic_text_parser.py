# src/infrastructure/parsers/generic_text_parser.py
"""
Generic Text Parser Module

Advanced generic text parser with comprehensive table detection for multiple formats.
Supports Markdown tables, TSV, space-separated columns, and mixed formats.
"""

import re
from typing import Tuple, List, Optional
from src.core.models import DocumentTable
from .base_parser import BaseParser


class GenericTextParser(BaseParser):
    """
    Advanced generic text parser with comprehensive table detection.
    
    Features:
    - Extensive encoding support for maximum compatibility
    - Multi-format table detection (Markdown, TSV, space-separated)
    - Enhanced pattern recognition with intelligent heuristics
    - Robust error handling and graceful degradation
    - Advanced table analysis and classification
    """
    
    def __init__(self):
        """Initialize generic text parser."""
        super().__init__()
        # Extended encoding list for maximum compatibility
        self.encodings = [
            'utf-8', 'utf-16', 'utf-16-le', 'utf-16-be',
            'utf-32', 'utf-32-le', 'utf-32-be',
            'latin-1', 'cp1252', 'iso-8859-1', 'iso-8859-15',
            'ascii', 'cp437', 'cp850', 'cp1251', 'mac-roman'
        ]
    
    def parse(self, content: bytes) -> Tuple[str, bool, str]:
        """
        Parse any text-based content with comprehensive encoding detection.
        
        Args:
            content: File content as bytes
            
        Returns:
            Tuple of (extracted_text, used_ocr, processing_method)
        """
        if not self._validate_content(content):
            return "Error: Invalid content", False, "text_extraction"
        
        # Try each encoding with validation
        for encoding in self.encodings:
            try:
                text = content.decode(encoding)
                if self._is_valid_text(text):
                    return text, False, "text_extraction"
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        # Final fallback with error handling
        try:
            text = content.decode('utf-8', errors='replace')
            return text, False, "text_extraction"
        except Exception as e:
            return f"Error: Could not decode file content - {str(e)}", False, "text_extraction"
    
    def _is_valid_text(self, text: str) -> bool:
        """
        Validate decoded text quality with enhanced checks.
        
        Args:
            text: Decoded text string
            
        Returns:
            True if text appears to be valid
        """
        if not text:
            return False
        
        # Check for excessive null characters
        null_ratio = text.count('\x00') / max(len(text), 1)
        if null_ratio > 0.1:
            return False
        
        # Check printable character ratio
        printable_chars = sum(1 for c in text if c.isprintable() or c.isspace())
        printable_ratio = printable_chars / max(len(text), 1)
        
        # Check for reasonable line structure
        lines = text.split('\n')
        if len(lines) > 1:
            avg_line_length = sum(len(line) for line in lines) / len(lines)
            # Reject if average line length is too short (likely binary data)
            if avg_line_length < 5 and printable_ratio < 0.9:
                return False
        
        return printable_ratio > 0.7
    
    def count_pages(self, content: bytes) -> int:
        """
        Estimate pages based on content length and structure.
        
        Args:
            content: File content as bytes
            
        Returns:
            Estimated number of pages
        """
        if not self._validate_content(content):
            return 0
        
        try:
            text = content.decode('utf-8', errors='ignore')
            lines = text.count('\n') + 1
            
            # More sophisticated page estimation
            if lines < 50:
                return 1
            elif lines < 200:
                return max(1, lines // 50)
            else:
                # For longer documents, consider content density
                chars_per_line = len(text) / lines
                if chars_per_line > 80:  # Dense content
                    return max(1, lines // 40)
                else:  # Sparse content
                    return max(1, lines // 60)
                    
        except Exception:
            return 1
    
    def extract_tables(self, content: bytes) -> List[DocumentTable]:
        """
        Advanced table detection for generic text files.
        
        Supports multiple formats:
        - Markdown tables (| separated)
        - Tab-separated values
        - Space-separated columns (3+ spaces)
        - Mixed formats with intelligent detection
        
        Args:
            content: File content as bytes
            
        Returns:
            List of DocumentTable objects
        """
        if not self._validate_content(content):
            return []
        
        try:
            text = content.decode('utf-8', errors='ignore')
            lines = text.split('\n')
            
            tables = []
            table_lines = []
            table_index = 0
            in_table = False
            
            for line_num, line in enumerate(lines):
                original_line = line
                line = line.strip()
                
                # Enhanced table row detection
                is_table_row = self._is_table_row(line)
                
                if is_table_row:
                    if not in_table:
                        in_table = True
                    table_lines.append(original_line.strip())
                else:
                    # End of table
                    if in_table and len(table_lines) >= 2:
                        table = self._parse_generic_table(table_lines, table_index)
                        if table:
                            tables.append(table)
                            table_index += 1
                    
                    table_lines = []
                    in_table = False
            
            # Check for table at end of file
            if in_table and len(table_lines) >= 2:
                table = self._parse_generic_table(table_lines, table_index)
                if table:
                    tables.append(table)
            
            return tables
            
        except Exception as e:
            print(f"Generic text table extraction error: {e}")
            return []
    
    def _is_table_row(self, line: str) -> bool:
        """
        Enhanced table row detection with multiple format support.
        
        Args:
            line: Text line to analyze
            
        Returns:
            True if line appears to be part of a table
        """
        if not line or len(line) < 3:
            return False
        
        # Markdown table detection (| separated)
        if '|' in line and line.count('|') >= 2:
            return True
        
        # Tab-separated detection
        if '\t' in line and line.count('\t') >= 1:
            return True
        
        # Space-separated detection (3+ consecutive spaces as separator)
        if len(line.split()) >= 3 and re.search(r'\s{3,}', line):
            return True
        
        # Markdown separator line detection (---|---|---)
        if line and '---' in line and set(line.strip()) <= set('|-+ '):
            return True
        
        # Comma-separated detection (for CSV-like content)
        if ',' in line and line.count(',') >= 2:
            # Additional validation to avoid false positives
            parts = line.split(',')
            if len(parts) >= 3 and all(len(part.strip()) > 0 for part in parts[:3]):
                return True
        
        return False
    
    def _parse_generic_table(self, table_lines: List[str], table_index: int) -> Optional[DocumentTable]:
        """
        Parse table from generic text with enhanced detection and validation.
        
        Args:
            table_lines: Lines that form the table
            table_index: Index of table in document
            
        Returns:
            DocumentTable object or None
        """
        if not table_lines:
            return None
        
        try:
            # Filter out markdown separator lines
            data_lines = self._filter_separator_lines(table_lines)
            
            if not data_lines:
                return None
            
            # Determine separator type and parse rows
            separator_type = self._determine_separator_type(data_lines[0])
            
            if not separator_type:
                return None
            
            rows = self._parse_rows_by_separator(data_lines, separator_type)
            
            if len(rows) < 1:
                return None
            
            # Separate headers from data
            headers, data_rows = self._separate_headers_and_data(rows)
            
            # Validate table structure
            if not self._validate_table_structure(headers, data_rows):
                return None
            
            # Create table representations
            table_text = self._create_table_text(headers, data_rows)
            table_html = self._create_table_html(headers, data_rows)
            table_markdown = self._create_table_markdown(headers, data_rows)
            table_csv = self._create_table_csv(headers, data_rows)
            
            # Analyze table using mixin methods
            table_type = self._detect_table_type(headers, data_rows)
            column_types = self._detect_column_types(data_rows) if data_rows else []
            data_quality = self._assess_data_quality(data_rows) if data_rows else 0.5
            
            return DocumentTable(
                table_index=table_index,
                page_number=None,
                headers=headers,
                rows=data_rows,
                row_count=len(data_rows),
                column_count=len(headers) if headers else (len(data_rows[0]) if data_rows else 0),
                column_types=column_types,
                data_quality_score=data_quality,
                table_text=table_text.strip(),
                table_html=table_html,
                table_markdown=table_markdown,
                table_csv=table_csv,
                table_type=table_type,
                confidence_score=0.8,  # Good confidence for structured text
                extraction_method="text_pattern",
                processing_time_ms=30
            )
            
        except Exception as e:
            # Only log significant errors, not CSV parsing issues
            if "escapechar" not in str(e).lower():
                logger.debug(f"Generic table parsing failed: {e}")
            return None
    
    def _filter_separator_lines(self, table_lines: List[str]) -> List[str]:
        """
        Filter out markdown separator lines and empty lines.
        
        Args:
            table_lines: Raw table lines
            
        Returns:
            Filtered lines containing actual data
        """
        data_lines = []
        for line in table_lines:
            line = line.strip()
            
            # Skip markdown separator lines (|---|---|)
            if '---' in line and set(line.strip()) <= set('|-+ '):
                continue
            
            # Skip empty lines
            if not line:
                continue
            
            data_lines.append(line)
        
        return data_lines
    
    def _determine_separator_type(self, line: str) -> Optional[str]:
        """
        Determine the separator type for table parsing.
        
        Args:
            line: Sample line to analyze
            
        Returns:
            Separator type or None
        """
        # Priority order for separator detection
        if '|' in line and line.count('|') >= 2:
            return 'pipe'
        elif '\t' in line:
            return 'tab'
        elif ',' in line and line.count(',') >= 2:
            return 'comma'
        elif re.search(r'\s{3,}', line):  # 3+ spaces
            return 'space'
        
        return None
    
    def _parse_rows_by_separator(self, data_lines: List[str], separator_type: str) -> List[List[str]]:
        """
        Parse rows based on detected separator type.
        
        Args:
            data_lines: Lines to parse
            separator_type: Type of separator to use
            
        Returns:
            List of parsed rows
        """
        rows = []
        
        for line in data_lines:
            cells = []
            
            if separator_type == 'pipe':
                line = line.strip().strip('|')
                cells = [cell.strip() for cell in line.split('|')]
            elif separator_type == 'tab':
                cells = [cell.strip() for cell in line.split('\t')]
            elif separator_type == 'comma':
                # Simple CSV parsing (not handling quoted commas)
                cells = [cell.strip() for cell in line.split(',')]
            elif separator_type == 'space':
                cells = re.split(r'\s{3,}', line.strip())
                cells = [cell.strip() for cell in cells]
            
            # Add non-empty rows with consistent column count
            if cells and any(cell.strip() for cell in cells):
                # Ensure consistent column count
                if not rows or len(cells) == len(rows[0]):
                    rows.append(cells)
                elif len(rows) > 0:
                    # Try to handle inconsistent column counts
                    expected_cols = len(rows[0])
                    if len(cells) < expected_cols:
                        # Pad with empty cells
                        cells.extend([''] * (expected_cols - len(cells)))
                    elif len(cells) > expected_cols:
                        # Truncate extra cells
                        cells = cells[:expected_cols]
                    rows.append(cells)
        
        return rows
    
    def _separate_headers_and_data(self, rows: List[List[str]]) -> tuple:
        """
        Separate headers from data rows with enhanced heuristics.
        
        Args:
            rows: All table rows
            
        Returns:
            Tuple of (headers, data_rows)
        """
        if len(rows) <= 1:
            return None, rows
        
        first_row = rows[0]
        
        # Enhanced header detection heuristics
        header_indicators = 0
        
        # Check if first row looks like headers
        for cell in first_row:
            if not cell.strip():
                continue
            
            # Headers typically don't contain numbers (except years)
            if not (cell.replace('%', '').replace('$', '').replace(',', '').replace('.', '').isdigit()):
                header_indicators += 1
            
            # Headers are typically shorter
            if len(cell) < 50:
                header_indicators += 0.5
            
            # Headers often contain descriptive words
            if any(word in cell.lower() for word in ['name', 'type', 'date', 'amount', 'total', 'count']):
                header_indicators += 1
        
        # If majority of cells look like headers, treat first row as headers
        if header_indicators >= len([c for c in first_row if c.strip()]) * 0.6:
            return first_row, rows[1:]
        
        return None, rows
    
    def _validate_table_structure(self, headers: Optional[List[str]], data_rows: List[List[str]]) -> bool:
        """
        Validate table structure for quality assurance.
        
        Args:
            headers: Table headers (if any)
            data_rows: Table data rows
            
        Returns:
            True if table structure is valid
        """
        # Must have at least one row
        if not data_rows and not headers:
            return False
        
        # Check for consistent column count
        if data_rows:
            expected_cols = len(data_rows[0])
            for row in data_rows[1:]:
                if len(row) != expected_cols:
                    return False
        
        # Headers should match data column count
        if headers and data_rows:
            if len(headers) != len(data_rows[0]):
                return False
        
        # Check for minimum content
        if data_rows:
            non_empty_cells = sum(1 for row in data_rows for cell in row if cell.strip())
            total_cells = sum(len(row) for row in data_rows)
            if total_cells > 0 and non_empty_cells / total_cells < 0.3:  # Less than 30% content
                return False
        
        return True