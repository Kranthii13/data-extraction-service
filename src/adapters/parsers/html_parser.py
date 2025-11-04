"""
HTML Parser - Extract tables from HTML content
Handles HTML files and HTML-based documents (like Confluence exports)
"""

import re
from typing import Tuple, List
from bs4 import BeautifulSoup
import html
import quopri
from src.core.models import DocumentTable
from .base_parser import BaseParser

class HtmlParser(BaseParser):
    """Parser for HTML content with table extraction capabilities"""
    
    def __init__(self):
        super().__init__()
    
    def parse(self, content: bytes) -> Tuple[str, bool, str]:
        """
        Parse HTML content and extract text
        
        Args:
            content: HTML content as bytes
            
        Returns:
            Tuple of (extracted_text, used_ocr, processing_method)
        """
        try:
            # Decode the content
            text_content = self._decode_content(content)
            
            # Parse HTML and extract text
            soup = BeautifulSoup(text_content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text content
            text = soup.get_text()
            
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            return text, False, "html_extraction"
            
        except Exception as e:
            # Fallback to raw text
            try:
                text_content = content.decode('utf-8', errors='ignore')
                return text_content, False, "text_extraction"
            except:
                return str(content), False, "raw_extraction"
    
    def count_pages(self, content: bytes) -> int:
        """
        Count pages in HTML document (estimate based on content length)
        
        Args:
            content: HTML content as bytes
            
        Returns:
            Estimated number of pages
        """
        text, _, _ = self.parse(content)
        # Rough estimate: 500 words per page
        word_count = len(text.split())
        return max(1, word_count // 500)
    
    def extract_tables(self, content: bytes) -> List[DocumentTable]:
        """
        Extract tables from HTML content
        
        Args:
            content: HTML content as bytes
            
        Returns:
            List of DocumentTable objects
        """
        try:
            # Decode the content
            text_content = self._decode_content(content)
            
            # Parse HTML
            soup = BeautifulSoup(text_content, 'html.parser')
            
            # Find all tables
            tables = soup.find_all('table')
            
            extracted_tables = []
            
            for table_idx, table in enumerate(tables):
                try:
                    # Extract table data
                    table_data = self._extract_table_data(table, table_idx)
                    if table_data:
                        extracted_tables.append(table_data)
                except Exception as e:
                    print(f"Warning: Failed to extract table {table_idx}: {e}")
                    continue
            
            return extracted_tables
            
        except Exception as e:
            print(f"Error extracting tables from HTML: {e}")
            return []
    
    def _decode_content(self, content: bytes) -> str:
        """
        Decode HTML content, handling various encodings and formats
        
        Args:
            content: Raw content bytes
            
        Returns:
            Decoded text content
        """
        try:
            # First try UTF-8
            text_content = content.decode('utf-8')
        except UnicodeDecodeError:
            try:
                # Try latin-1
                text_content = content.decode('latin-1')
            except UnicodeDecodeError:
                # Fallback with error handling
                text_content = content.decode('utf-8', errors='ignore')
        
        # Handle quoted-printable encoding (common in email/MIME)
        if 'quoted-printable' in text_content.lower():
            try:
                # Extract the HTML part
                html_start = text_content.find('<html')
                if html_start > 0:
                    html_part = text_content[html_start:]
                    # Decode quoted-printable
                    decoded = quopri.decodestring(html_part.encode()).decode('utf-8', errors='ignore')
                    text_content = decoded
            except Exception:
                pass
        
        # Handle HTML entities
        text_content = html.unescape(text_content)
        
        return text_content
    
    def _extract_table_data(self, table, table_idx: int) -> DocumentTable:
        """
        Extract data from a single HTML table
        
        Args:
            table: BeautifulSoup table element
            table_idx: Index of the table in the document
            
        Returns:
            DocumentTable object or None if extraction fails
        """
        try:
            # Find all rows
            rows = table.find_all('tr')
            if not rows:
                return None
            
            # Extract headers (first row or th elements)
            headers = []
            data_rows = []
            
            # Check if first row contains th elements (headers)
            first_row = rows[0]
            th_elements = first_row.find_all('th')
            
            if th_elements:
                # First row is headers
                headers = [self._clean_cell_text(th.get_text()) for th in th_elements]
                data_rows = rows[1:]
            else:
                # No explicit headers, use first row as headers
                td_elements = first_row.find_all(['td', 'th'])
                if td_elements:
                    headers = [self._clean_cell_text(td.get_text()) for td in td_elements]
                    data_rows = rows[1:]
                else:
                    # No headers, treat all rows as data
                    headers = [f"Column {i+1}" for i in range(len(first_row.find_all(['td', 'th'])))]
                    data_rows = rows
            
            # Extract data rows
            table_rows = []
            for row in data_rows:
                cells = row.find_all(['td', 'th'])
                if cells:
                    row_data = [self._clean_cell_text(cell.get_text()) for cell in cells]
                    # Ensure row has same number of columns as headers
                    while len(row_data) < len(headers):
                        row_data.append("")
                    table_rows.append(row_data[:len(headers)])  # Truncate if too long
            
            # Skip empty tables
            if not table_rows or not headers:
                return None
            
            # Get table context
            context = self._get_table_context(table)
            
            # Create DocumentTable
            return DocumentTable(
                table_index=table_idx,
                headers=headers,
                rows=table_rows,
                row_count=len(table_rows),
                column_count=len(headers),
                title=context.get('title', ''),
                context_before=context.get('before', ''),
                context_after=context.get('after', ''),
                table_type=self._classify_table_type(headers, table_rows),
                confidence_score=0.95,  # High confidence for HTML tables
                extraction_method="html_parser"
            )
            
        except Exception as e:
            print(f"Error extracting table {table_idx}: {e}")
            return None
    
    def _clean_cell_text(self, text: str) -> str:
        """
        Clean text content from table cells
        
        Args:
            text: Raw cell text
            
        Returns:
            Cleaned text
        """
        if not text:
            return ""
        
        # Remove extra whitespace and newlines
        cleaned = re.sub(r'\s+', ' ', text.strip())
        
        # Remove common HTML artifacts
        cleaned = cleaned.replace('\n', ' ').replace('\r', ' ')
        
        return cleaned
    
    def _get_table_context(self, table) -> dict:
        """
        Extract context around the table (title, surrounding text)
        
        Args:
            table: BeautifulSoup table element
            
        Returns:
            Dictionary with context information
        """
        context = {'title': '', 'before': '', 'after': ''}
        
        try:
            # Look for table caption or title
            caption = table.find('caption')
            if caption:
                context['title'] = self._clean_cell_text(caption.get_text())
            
            # Look for preceding heading or paragraph
            prev_element = table.find_previous(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p'])
            if prev_element:
                prev_text = self._clean_cell_text(prev_element.get_text())
                if len(prev_text) < 200:  # Only use short text as context
                    context['before'] = prev_text
            
            # Look for table wrapper with title
            wrapper = table.find_parent(['div', 'section'])
            if wrapper:
                # Look for heading in wrapper
                heading = wrapper.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                if heading and not context['title']:
                    context['title'] = self._clean_cell_text(heading.get_text())
        
        except Exception:
            pass
        
        return context
    
    def _classify_table_type(self, headers: List[str], rows: List[List[str]]) -> str:
        """
        Classify table type based on content
        
        Args:
            headers: Table headers
            rows: Table data rows
            
        Returns:
            Table type classification
        """
        header_text = " ".join(headers).lower()
        
        # Classification keywords
        if any(word in header_text for word in ['status', 'done', 'completed', 'pending']):
            return "status"
        elif any(word in header_text for word in ['item', 'feature', 'task', 'requirement']):
            return "requirements"
        elif any(word in header_text for word in ['name', 'person', 'author', 'assignee']):
            return "assignments"
        elif any(word in header_text for word in ['date', 'time', 'deadline', 'due']):
            return "schedule"
        else:
            return "data"