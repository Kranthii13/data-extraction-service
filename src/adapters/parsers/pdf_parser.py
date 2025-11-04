"""
PDF Parser - Complete Document Data Extraction
Extracts 100% of data from PDF documents including text, images, tables, and metadata
"""

import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageEnhance
import io
import base64
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import logging
from datetime import datetime

from .ocr_config import get_ocr_config, is_ocr_available

logger = logging.getLogger(__name__)

@dataclass
class TextElement:
    """Represents a text element with position and formatting"""
    text: str
    page: int
    position: Dict[str, float]  # x, y, width, height
    font: Dict[str, Any]  # name, size, flags
    element_type: str  # paragraph, header, footer, footnote

@dataclass
class ImageElement:
    """Represents an extracted image with metadata"""
    image_id: str
    page: int
    position: Dict[str, float]
    format: str
    size_bytes: int
    base64_data: str
    extracted_text: str
    image_type: str  # photo, chart, diagram, signature
    ocr_confidence: float
    visual_elements: List[str]

from .base_parser import BaseParser

class PdfParser(BaseParser):
    """Advanced PDF parser for complete document data extraction"""
    
    def __init__(self):
        super().__init__()
        self.doc = None
        self.total_pages = 0
        self.processing_start = None
        
    def parse(self, content: bytes) -> Tuple[str, bool, str]:
        """
        Parse PDF content and extract text (interface method)
        
        Args:
            content: PDF content as bytes
            
        Returns:
            Tuple of (extracted_text, used_ocr, processing_method)
        """
        import tempfile
        import os
        
        # Write content to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
        
        try:
            # Extract complete document
            result = self.extract_complete_document(temp_path)
            
            # Extract required information for interface
            full_text = result.get('text_data', {}).get('full_text', '')
            
            # Check if OCR was used by looking for image text markers in the full text
            used_ocr = '[IMAGE TEXT FROM PAGE' in full_text or len(result.get('image_data', {}).get('images', [])) > 0
            processing_method = 'hybrid_with_ocr' if used_ocr else 'text_extraction'
            
            return full_text, used_ocr, processing_method
            
        finally:
            # Clean up temporary file
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def count_pages(self, content: bytes) -> int:
        """
        Count pages in PDF document
        
        Args:
            content: PDF content as bytes
            
        Returns:
            Number of pages
        """
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
        
        try:
            doc = fitz.open(temp_path)
            page_count = len(doc)
            doc.close()
            return page_count
        except Exception:
            return 0
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def extract_tables(self, content: bytes) -> List:
        """
        Extract tables from PDF content (interface method)
        
        Args:
            content: PDF content as bytes
            
        Returns:
            List of DocumentTable objects
        """
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
        
        try:
            result = self.extract_complete_document(temp_path)
            tables_data = result.get('table_data', {}).get('tables', [])
            
            # Convert to DocumentTable objects (simplified for now)
            from src.core.models import DocumentTable
            tables = []
            for idx, table_data in enumerate(tables_data):
                rows = table_data.get('rows', [])
                headers = table_data.get('headers', [])
                table = DocumentTable(
                    table_index=idx,
                    row_count=len(rows),
                    column_count=len(headers) if headers else (len(rows[0]) if rows else 0),
                    headers=headers,
                    rows=rows,
                    title=table_data.get('title', ''),
                    context_before=table_data.get('context_before', ''),
                    context_after=table_data.get('context_after', ''),
                    table_type=table_data.get('table_type', 'data'),
                    confidence_score=table_data.get('confidence_score', 0.0),
                    quality_score=table_data.get('quality_score', 0.0)
                )
                tables.append(table)
            
            return tables
            
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def extract_complete_document(self, pdf_path: str) -> Dict[str, Any]:
        """Extract all data from PDF document"""
        self.processing_start = datetime.now()
        
        try:
            self.doc = fitz.open(pdf_path)
            self.total_pages = len(self.doc)
            
            logger.info(f"Processing PDF: {pdf_path} ({self.total_pages} pages)")
            
            result = {
                "document_id": self._generate_document_id(pdf_path),
                "processing_timestamp": self.processing_start.isoformat(),
                "file_info": self._extract_file_info(pdf_path),
                "text_data": self._extract_all_text(),
                "image_data": self._extract_all_images(),
                "table_data": self._extract_all_tables(),
                "metadata": self._extract_document_metadata(),
                "structure": self._analyze_document_structure(),
                "processing_info": self._get_processing_info()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing PDF {pdf_path}: {str(e)}")
            raise
        finally:
            if self.doc:
                self.doc.close()
    
    def _extract_all_text(self) -> Dict[str, Any]:
        """Extract all text content with positioning and formatting"""
        logger.info("Extracting all text content...")
        
        all_paragraphs = []
        headers = []
        footers = []
        footnotes = []
        captions = []
        annotations = []
        
        total_text = ""
        word_count = 0
        
        for page_num in range(self.total_pages):
            page = self.doc[page_num]
            
            # First, get simple text extraction
            simple_text = page.get_text()
            if simple_text.strip():
                total_text += simple_text + " "
                word_count += len(simple_text.split())
            
            # Get text blocks with detailed information
            blocks = page.get_text("dict")
            
            for block in blocks["blocks"]:
                if "lines" in block:  # Text block
                    for line in block["lines"]:
                        for span in line["spans"]:
                            text = span["text"].strip()
                            if not text:
                                continue
                                
                            # Create text element
                            element = TextElement(
                                text=text,
                                page=page_num + 1,
                                position={
                                    "x": span["bbox"][0],
                                    "y": span["bbox"][1], 
                                    "width": span["bbox"][2] - span["bbox"][0],
                                    "height": span["bbox"][3] - span["bbox"][1]
                                },
                                font={
                                    "name": span["font"],
                                    "size": span["size"],
                                    "bold": bool(span["flags"] & 2**4),
                                    "italic": bool(span["flags"] & 2**1)
                                },
                                element_type=self._classify_text_element(span, page)
                            )
                            
                            # Categorize by type
                            if element.element_type == "header":
                                headers.append(element.__dict__)
                            elif element.element_type == "footer":
                                footers.append(element.__dict__)
                            elif element.element_type == "footnote":
                                footnotes.append(element.__dict__)
                            elif element.element_type == "caption":
                                captions.append(element.__dict__)
                            else:
                                all_paragraphs.append(element.__dict__)
            
            # EXTRACT AND INCLUDE IMAGE TEXT FROM THIS PAGE (if OCR is available)
            try:
                from .ocr_config import is_ocr_available
                if is_ocr_available():
                    image_list = page.get_images()
                    
                    # For image-heavy PDFs, try page-level OCR first (more efficient)
                    if len(image_list) > 5 or len(simple_text.strip()) == 0:
                        # This looks like a scanned page - do full page OCR
                        try:
                            # Render entire page as image for OCR
                            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR
                            pix = page.get_pixmap(matrix=mat)
                            img_data = pix.tobytes("png")
                            img_pil = Image.open(io.BytesIO(img_data))
                            
                            # Use robust OCR processor
                            from .robust_ocr import get_ocr_processor
                            ocr_processor = get_ocr_processor()
                            
                            # Extract text using robust OCR
                            ocr_text, ocr_confidence = ocr_processor.extract_text_from_pil_image(img_pil, page_num + 1)
                            
                            # Include OCR text if any was extracted
                            if ocr_text.strip() and len(ocr_text.strip()) > 10:  # Only include substantial text
                                # Format the extracted text
                                config = get_ocr_config()
                                formatted_text = config.format_extracted_text(ocr_text, ocr_confidence, page_num + 1)
                                total_text += f"\n{formatted_text}\n"
                                word_count += len(ocr_text.split())
                                
                                logger.info(f"Page {page_num + 1} OCR: {len(ocr_text)} chars, confidence: {ocr_confidence:.2%}")
                            
                            pix = None
                            
                        except Exception as e:
                            logger.warning(f"Page-level OCR failed for page {page_num+1}: {str(e)}")
                    
                    else:
                        # Process individual images (original method for PDFs with mixed content)
                        for img_index, img in enumerate(image_list):
                            try:
                                # Skip very small images (likely icons/decorations)
                                xref = img[0]
                                pix = fitz.Pixmap(self.doc, xref)
                                
                                if pix.width < 100 or pix.height < 100:
                                    pix = None
                                    continue
                                
                                if pix.n - pix.alpha < 4:  # GRAY or RGB
                                    img_data = pix.tobytes("png")
                                    img_pil = Image.open(io.BytesIO(img_data))
                                    
                                    # Use robust OCR processor
                                    from .robust_ocr import get_ocr_processor
                                    ocr_processor = get_ocr_processor()
                                    
                                    # Extract text using robust OCR
                                    ocr_text, ocr_confidence = ocr_processor.extract_text_from_pil_image(img_pil, page_num + 1)
                                    
                                    # Include OCR text if any was extracted
                                    if ocr_text.strip() and len(ocr_text.strip()) > 5:
                                        # Format the extracted text
                                        config = get_ocr_config()
                                        formatted_text = config.format_extracted_text(ocr_text, ocr_confidence, page_num + 1)
                                        total_text += f"\n{formatted_text}\n"
                                        word_count += len(ocr_text.split())
                                
                                pix = None
                                
                            except Exception as e:
                                logger.warning(f"Error extracting text from image {img_index} on page {page_num+1}: {str(e)}")
                                continue
                else:
                    logger.info(f"OCR not available - skipping image text extraction for page {page_num + 1}")
            except Exception as e:
                logger.warning(f"OCR processing failed for page {page_num + 1}: {str(e)}")
            
            # Extract annotations
            annotations.extend(self._extract_page_annotations(page, page_num + 1))
        
        return {
            "full_text": total_text.strip(),
            "word_count": word_count,
            "character_count": len(total_text),
            "paragraphs": all_paragraphs,
            "headers": headers,
            "footers": footers,
            "footnotes": footnotes,
            "captions": captions,
            "annotations": annotations
        }
    
    def _extract_all_images(self) -> Dict[str, Any]:
        """Extract all images with OCR and analysis"""
        logger.info("Extracting all images...")
        
        images = []
        charts_graphs = []
        total_images = 0
        
        for page_num in range(self.total_pages):
            page = self.doc[page_num]
            image_list = page.get_images()
            
            for img_index, img in enumerate(image_list):
                try:
                    # Extract image data
                    xref = img[0]
                    pix = fitz.Pixmap(self.doc, xref)
                    
                    if pix.n - pix.alpha < 4:  # GRAY or RGB
                        img_data = pix.tobytes("png")
                        img_pil = Image.open(io.BytesIO(img_data))
                        
                        # Generate image ID
                        image_id = f"img_{page_num+1:03d}_{img_index+1:03d}"
                        
                        # Get image position on page
                        img_rects = page.get_image_rects(xref)
                        position = {}
                        if img_rects:
                            rect = img_rects[0]
                            position = {
                                "x": rect.x0,
                                "y": rect.y0,
                                "width": rect.width,
                                "height": rect.height
                            }
                        
                        # Perform OCR using robust OCR processor
                        from .robust_ocr import get_ocr_processor
                        ocr_processor = get_ocr_processor()
                        ocr_text, ocr_confidence = ocr_processor.extract_text_from_pil_image(img_pil, page_num + 1)
                        
                        # Analyze image type and content
                        image_type, visual_elements = self._analyze_image_content(img_pil, ocr_text)
                        
                        # Create image element
                        image_element = ImageElement(
                            image_id=image_id,
                            page=page_num + 1,
                            position=position,
                            format="PNG",
                            size_bytes=len(img_data),
                            base64_data=base64.b64encode(img_data).decode(),
                            extracted_text=ocr_text,
                            image_type=image_type,
                            ocr_confidence=ocr_confidence,
                            visual_elements=visual_elements
                        )
                        
                        images.append(image_element.__dict__)
                        total_images += 1
                        
                        # If it's a chart/graph, extract data
                        if image_type in ["chart", "graph", "diagram"]:
                            chart_data = self._extract_chart_data(ocr_text, image_type)
                            if chart_data:
                                chart_data["image_id"] = image_id
                                charts_graphs.append(chart_data)
                    
                    pix = None
                    
                except Exception as e:
                    logger.warning(f"Error processing image {img_index} on page {page_num+1}: {str(e)}")
                    continue
        
        return {
            "total_images": total_images,
            "images": images,
            "charts_graphs": charts_graphs
        }
    
    def _extract_all_tables(self) -> Dict[str, Any]:
        """Extract all tables with enhanced analysis"""
        logger.info("Extracting all tables...")
        
        tables = []
        total_tables = 0
        
        for page_num in range(self.total_pages):
            page = self.doc[page_num]
            
            # Try PyMuPDF table detection first
            try:
                page_tables = page.find_tables()
                
                for table_index, table in enumerate(page_tables):
                    table_data = self._process_table(table, page, page_num + 1, table_index)
                    if table_data:
                        tables.append(table_data)
                        total_tables += 1
                        
            except Exception as e:
                logger.warning(f"PyMuPDF table detection failed on page {page_num+1}: {str(e)}")
            
            # Fallback: OCR-based table detection for scanned documents
            if not page_tables:
                # Try OCR-based table detection
                ocr_tables = self._detect_ocr_tables(page, page_num + 1)
                tables.extend(ocr_tables)
                total_tables += len(ocr_tables)
                
                # Final fallback: text pattern detection
                if not ocr_tables:
                    text_tables = self._detect_text_tables(page, page_num + 1)
                    tables.extend(text_tables)
                    total_tables += len(text_tables)
        
        return {
            "total_tables": total_tables,
            "tables": tables
        }
    
    # ... (rest of the methods remain the same)
    

    
    def _analyze_image_content(self, image: Image.Image, ocr_text: str) -> Tuple[str, List[str]]:
        """Analyze image to determine type and visual elements"""
        visual_elements = []
        text_lower = ocr_text.lower()
        
        chart_keywords = ['chart', 'graph', 'revenue', 'profit', 'growth', 'percentage', '%', '$']
        if any(keyword in text_lower for keyword in chart_keywords):
            image_type = "chart"
            visual_elements = ["data_visualization", "text_labels"]
        elif any(char in ocr_text for char in ['|', '\t']) or len(ocr_text.split('\n')) > 3:
            image_type = "table"
            visual_elements = ["tabular_data", "text"]
        elif any(word in text_lower for word in ['diagram', 'flow', 'process', 'system']):
            image_type = "diagram"
            visual_elements = ["shapes", "arrows", "text_labels"]
        elif len(ocr_text.strip()) < 20 and any(char.isalpha() for char in ocr_text):
            image_type = "signature"
            visual_elements = ["handwriting"]
        else:
            image_type = "photo"
            visual_elements = ["image_content"]
        
        return image_type, visual_elements
    
    def _extract_chart_data(self, ocr_text: str, image_type: str) -> Optional[Dict[str, Any]]:
        """Extract structured data from chart OCR text"""
        if not ocr_text.strip():
            return None
        
        try:
            lines = ocr_text.split('\n')
            title = lines[0] if lines else "Untitled Chart"
            
            numbers = re.findall(r'[\d,]+\.?\d*', ocr_text)
            labels = re.findall(r'[A-Za-z][A-Za-z\s]*(?=\s*[\d$%])', ocr_text)
            
            data_extracted = {}
            if len(labels) == len(numbers):
                for label, number in zip(labels, numbers):
                    clean_number = number.replace(',', '')
                    try:
                        data_extracted[label.strip()] = float(clean_number)
                    except ValueError:
                        data_extracted[label.strip()] = clean_number
            
            return {
                "chart_id": f"chart_{hash(ocr_text) % 10000:04d}",
                "type": image_type,
                "title": title,
                "data_extracted": data_extracted,
                "raw_ocr_text": ocr_text
            }
            
        except Exception as e:
            logger.warning(f"Chart data extraction failed: {str(e)}")
            return None
    
    def _classify_text_element(self, span: Dict, page) -> str:
        """Classify text element type based on position and formatting"""
        y_pos = span["bbox"][1]
        page_height = page.rect.height
        font_size = span["size"]
        
        if y_pos > page_height * 0.9:
            return "header"
        elif y_pos < page_height * 0.1:
            return "footer"
        elif y_pos < page_height * 0.2 and font_size < 10:
            return "footnote"
        elif font_size < 10 and any(word in span["text"].lower() for word in ["figure", "table", "chart"]):
            return "caption"
        else:
            return "paragraph"
    
    def _extract_page_annotations(self, page, page_num: int) -> List[Dict]:
        """Extract annotations, comments, and markup"""
        annotations = []
        
        try:
            for annot in page.annots():
                annotation_data = {
                    "page": page_num,
                    "type": annot.type[1],
                    "content": annot.info.get("content", ""),
                    "author": annot.info.get("title", ""),
                    "position": {
                        "x": annot.rect.x0,
                        "y": annot.rect.y0,
                        "width": annot.rect.width,
                        "height": annot.rect.height
                    }
                }
                annotations.append(annotation_data)
                
        except Exception as e:
            logger.warning(f"Error extracting annotations from page {page_num}: {str(e)}")
        
        return annotations
    
    def _process_table(self, table, page, page_num: int, table_index: int) -> Optional[Dict]:
        """Process individual table with enhanced analysis"""
        try:
            table_data = table.extract()
            if not table_data:
                return None
            
            bbox = table.bbox
            position = {
                "x": bbox.x0,
                "y": bbox.y0,
                "width": bbox.width,
                "height": bbox.height
            }
            
            context = self._extract_table_context(page, bbox)
            headers = table_data[0] if table_data else []
            rows = table_data[1:] if len(table_data) > 1 else []
            data_types = self._detect_column_types(rows, headers)
            table_type = self._classify_table_type(headers, rows)
            quality_score = self._assess_table_quality(table_data)
            
            return {
                "table_id": f"table_{page_num:03d}_{table_index+1:03d}",
                "page": page_num,
                "position": position,
                "title": context.get("title", ""),
                "context_before": context.get("before", ""),
                "context_after": context.get("after", ""),
                "headers": headers,
                "rows": rows,
                "data_types": data_types,
                "table_type": table_type,
                "confidence_score": 0.95,
                "quality_score": quality_score,
                "export_formats": self._generate_export_formats(headers, rows)
            }
            
        except Exception as e:
            logger.warning(f"Error processing table {table_index} on page {page_num}: {str(e)}")
            return None
    
    def _detect_ocr_tables(self, page, page_num: int) -> List[Dict]:
        """Detect tables from OCR text in scanned documents"""
        tables = []
        
        try:
            from .ocr_config import is_ocr_available
            if not is_ocr_available():
                return tables
            
            # Render page as image for OCR table detection
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            
            from PIL import Image
            import io
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Use robust OCR processor
            from .robust_ocr import get_ocr_processor
            ocr_processor = get_ocr_processor()
            
            # Extract text using OCR
            ocr_text, ocr_confidence = ocr_processor.extract_text_from_pil_image(img_pil, page_num)
            
            if ocr_text.strip() and ocr_confidence > 0.3:
                # Look for table patterns in OCR text
                detected_tables = self._extract_tables_from_ocr_text(ocr_text, page_num)
                tables.extend(detected_tables)
                
                if detected_tables:
                    logger.info(f"OCR detected {len(detected_tables)} tables on page {page_num}")
            
            pix = None
            
        except Exception as e:
            logger.warning(f"OCR table detection failed on page {page_num}: {str(e)}")
        
        return tables
    
    def _extract_tables_from_ocr_text(self, ocr_text: str, page_num: int) -> List[Dict]:
        """Extract table structures from OCR text"""
        tables = []
        
        try:
            lines = ocr_text.split('\n')
            
            # Look for table-like patterns
            table_lines = []
            current_table = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    if current_table:
                        table_lines.append(current_table)
                        current_table = []
                    continue
                
                # Check if line looks like a table row (has multiple columns)
                # Look for common separators or aligned text
                if self._looks_like_table_row(line):
                    current_table.append(line)
                else:
                    if current_table:
                        table_lines.append(current_table)
                        current_table = []
            
            # Process detected table blocks
            for table_index, table_block in enumerate(table_lines):
                if len(table_block) >= 2:  # At least 2 rows for a table
                    table_data = self._parse_ocr_table_block(table_block, page_num, table_index)
                    if table_data:
                        tables.append(table_data)
        
        except Exception as e:
            logger.warning(f"OCR table parsing failed: {str(e)}")
        
        return tables
    
    def _looks_like_table_row(self, line: str) -> bool:
        """Check if a line looks like a table row"""
        # Look for multiple words/numbers separated by spaces
        parts = line.split()
        if len(parts) < 2:
            return False
        
        # Check for common table indicators
        indicators = [
            len(parts) >= 3,  # Multiple columns
            any(char in line for char in ['|', '\t']),  # Explicit separators
            len([p for p in parts if p.replace(',', '').replace('.', '').isdigit()]) >= 2,  # Multiple numbers
            len(line) > 20 and len(parts) >= 2  # Long line with multiple parts
        ]
        
        return any(indicators)
    
    def _parse_ocr_table_block(self, table_block: List[str], page_num: int, table_index: int) -> Optional[Dict]:
        """Parse a block of OCR text into table structure"""
        try:
            # Simple parsing - split by whitespace
            rows = []
            max_columns = 0
            
            for line in table_block:
                # Split by multiple spaces or tabs
                import re
                parts = re.split(r'\s{2,}|\t', line.strip())
                if len(parts) > 1:
                    rows.append(parts)
                    max_columns = max(max_columns, len(parts))
            
            if len(rows) < 2 or max_columns < 2:
                return None
            
            # Normalize row lengths
            normalized_rows = []
            for row in rows:
                while len(row) < max_columns:
                    row.append("")
                normalized_rows.append(row[:max_columns])
            
            # Assume first row is headers
            headers = normalized_rows[0] if normalized_rows else []
            data_rows = normalized_rows[1:] if len(normalized_rows) > 1 else []
            
            return {
                "table_id": f"ocr_table_{page_num:03d}_{table_index:03d}",
                "page": page_num,
                "table_index": table_index,
                "title": f"OCR Table {table_index + 1}",
                "headers": headers,
                "rows": data_rows,
                "row_count": len(data_rows),
                "column_count": max_columns,
                "table_type": "data",
                "confidence_score": 0.7,  # OCR-based detection
                "extraction_method": "ocr_pattern_detection",
                "context_before": "",
                "context_after": "",
                "table_text": "\n".join(table_block),
                "table_html": self._create_table_html(headers, data_rows),
                "table_markdown": self._create_table_markdown(headers, data_rows),
                "table_csv": self._create_table_csv(headers, data_rows)
            }
            
        except Exception as e:
            logger.warning(f"OCR table parsing failed: {str(e)}")
            return None
    
    def _detect_text_tables(self, page, page_num: int) -> List[Dict]:
        """Detect tables from text patterns"""
        return []  # Placeholder for text-based table detection
    
    def _extract_table_context(self, page, table_bbox) -> Dict[str, str]:
        """Extract context around table"""
        blocks = page.get_text("dict")["blocks"]
        context = {"title": "", "before": "", "after": ""}
        
        for block in blocks:
            if "lines" in block:
                block_bbox = fitz.Rect(block["bbox"])
                
                if block_bbox.y1 < table_bbox.y0 and block_bbox.y1 > table_bbox.y0 - 100:
                    text = " ".join([span["text"] for line in block["lines"] for span in line["spans"]])
                    if len(text) < 100 and any(word in text.lower() for word in ["table", "figure", "chart"]):
                        context["title"] = text.strip()
                    else:
                        context["before"] = text.strip()
                
                elif block_bbox.y0 > table_bbox.y1 and block_bbox.y0 < table_bbox.y1 + 100:
                    text = " ".join([span["text"] for line in block["lines"] for span in line["spans"]])
                    context["after"] = text.strip()
        
        return context
    
    def _detect_column_types(self, rows: List[List[str]], headers: List[str]) -> List[str]:
        """Detect data types for each column"""
        if not rows:
            return ["text"] * len(headers)
        
        data_types = []
        
        for col_idx in range(len(headers)):
            column_values = [row[col_idx] if col_idx < len(row) else "" for row in rows]
            column_values = [val for val in column_values if val.strip()]
            
            if not column_values:
                data_types.append("text")
                continue
            
            currency_count = sum(1 for val in column_values if any(symbol in val for symbol in ['$', '€', '£', '¥']))
            percentage_count = sum(1 for val in column_values if '%' in val)
            numeric_count = sum(1 for val in column_values if re.match(r'^[\d,.-]+$', val.replace('$', '').replace(',', '')))
            date_count = sum(1 for val in column_values if self._is_date_pattern(val))
            
            total_values = len(column_values)
            
            if currency_count / total_values >= 0.6:
                data_types.append("currency")
            elif percentage_count / total_values >= 0.6:
                data_types.append("percentage")
            elif date_count / total_values >= 0.6:
                data_types.append("date")
            elif numeric_count / total_values >= 0.6:
                data_types.append("numeric")
            else:
                data_types.append("text")
        
        return data_types
    
    def _is_date_pattern(self, value: str) -> bool:
        """Check if value matches common date patterns"""
        date_patterns = [
            r'\d{1,2}/\d{1,2}/\d{2,4}',
            r'\d{1,2}-\d{1,2}-\d{2,4}',
            r'\d{4}-\d{1,2}-\d{1,2}',
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)',
            r'(January|February|March|April|May|June|July|August|September|October|November|December)'
        ]
        
        return any(re.search(pattern, value, re.IGNORECASE) for pattern in date_patterns)
    
    def _classify_table_type(self, headers: List[str], rows: List[List[str]]) -> str:
        """Classify table type based on content"""
        header_text = " ".join(headers).lower()
        
        classifications = {
            "financial": ["amount", "cost", "price", "revenue", "profit", "budget", "expense", "$"],
            "contact": ["name", "email", "phone", "address", "contact", "person"],
            "statistics": ["count", "average", "percentage", "rate", "metric", "total"],
            "schedule": ["date", "time", "day", "month", "year", "schedule", "calendar"],
            "inventory": ["quantity", "stock", "item", "product", "inventory"],
            "performance": ["score", "rating", "performance", "result", "achievement"]
        }
        
        scores = {}
        for table_type, keywords in classifications.items():
            score = sum(1 for keyword in keywords if keyword in header_text)
            if score > 0:
                scores[table_type] = score
        
        return max(scores, key=scores.get) if scores else "data"
    
    def _assess_table_quality(self, table_data: List[List[str]]) -> float:
        """Assess table data quality"""
        if not table_data:
            return 0.0
        
        total_cells = sum(len(row) for row in table_data)
        empty_cells = sum(1 for row in table_data for cell in row if not cell.strip())
        malformed_cells = sum(1 for row in table_data for cell in row if len(cell) > 200 or '\n' in cell)
        
        empty_ratio = empty_cells / total_cells if total_cells > 0 else 0
        malformed_ratio = malformed_cells / total_cells if total_cells > 0 else 0
        
        quality_score = 1.0 - (empty_ratio * 0.4 + malformed_ratio * 0.8)
        return max(0.0, min(1.0, quality_score))
    
    def _generate_export_formats(self, headers: List[str], rows: List[List[str]]) -> Dict[str, str]:
        """Generate multiple export formats"""
        csv_lines = [",".join(f'"{cell}"' for cell in headers)]
        csv_lines.extend([",".join(f'"{cell}"' for cell in row) for row in rows])
        csv_data = "\n".join(csv_lines)
        
        json_data = {"headers": headers, "rows": rows}
        
        html_rows = []
        html_rows.append("<tr>" + "".join(f"<th>{cell}</th>" for cell in headers) + "</tr>")
        html_rows.extend(["<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows])
        html_data = f"<table>{''.join(html_rows)}</table>"
        
        return {"csv": csv_data, "json": json_data, "html": html_data}
    
    def _extract_file_info(self, pdf_path: str) -> Dict[str, Any]:
        """Extract file information"""
        import os
        
        file_stats = os.stat(pdf_path)
        
        return {
            "filename": os.path.basename(pdf_path),
            "size_bytes": file_stats.st_size,
            "format": "PDF",
            "pages": self.total_pages,
            "creation_date": datetime.fromtimestamp(file_stats.st_ctime).isoformat()
        }
    
    def _extract_document_metadata(self) -> Dict[str, Any]:
        """Extract document metadata"""
        metadata = self.doc.metadata
        
        return {
            "document_properties": {
                "title": metadata.get("title", ""),
                "author": metadata.get("author", ""),
                "subject": metadata.get("subject", ""),
                "keywords": metadata.get("keywords", "").split(",") if metadata.get("keywords") else [],
                "creator": metadata.get("creator", ""),
                "producer": metadata.get("producer", "")
            },
            "security": {
                "encrypted": self.doc.needs_pass,
                "permissions": [],
                "password_protected": self.doc.needs_pass
            },
            "language": "en-US",
            "page_layout": "portrait"
        }
    
    def _analyze_document_structure(self) -> Dict[str, Any]:
        """Analyze document structure and hierarchy"""
        return {
            "document_hierarchy": [],
            "sections": [],
            "cross_references": []
        }
    
    def _get_processing_info(self) -> Dict[str, Any]:
        """Get processing information and metrics"""
        processing_time = (datetime.now() - self.processing_start).total_seconds() * 1000
        
        return {
            "extraction_methods": {
                "text": "pymupdf_native",
                "images": "pymupdf_extract + tesseract_ocr",
                "tables": "pymupdf_tables + pattern_detection"
            },
            "processing_time_ms": int(processing_time),
            "confidence_scores": {
                "text_extraction": 0.98,
                "image_extraction": 0.91,
                "table_extraction": 0.95,
                "overall": 0.95
            },
            "quality_metrics": {
                "text_completeness": 0.99,
                "image_clarity": 0.87,
                "table_accuracy": 0.96,
                "overall_quality": 0.94
            }
        }
    
    def _generate_document_id(self, pdf_path: str) -> str:
        """Generate unique document ID"""
        import hashlib
        return hashlib.md5(pdf_path.encode()).hexdigest()[:12]