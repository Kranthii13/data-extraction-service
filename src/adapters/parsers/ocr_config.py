"""
OCR Configuration and Settings
"""

import os
from dataclasses import dataclass
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

@dataclass
class OCRConfig:
    """Configuration for OCR processing"""
    
    # OCR Engine settings
    enabled: bool = True
    confidence_threshold: float = 0.3  # Minimum confidence to include text
    
    # Image preprocessing
    enhance_contrast: bool = True
    enhance_sharpness: bool = True
    min_image_size: int = 300  # Minimum width/height for OCR
    
    # Tesseract configurations to try
    tesseract_configs: List[str] = None
    
    # Language settings
    languages: str = "eng"  # Tesseract language codes
    
    # Output formatting
    include_confidence_in_output: bool = False
    mark_image_text: bool = True  # Add [IMAGE TEXT] markers
    
    def __post_init__(self):
        if self.tesseract_configs is None:
            self.tesseract_configs = [
                r'--oem 3 --psm 6',   # Uniform block of text
                r'--oem 3 --psm 3',   # Fully automatic page segmentation
                r'--oem 3 --psm 8',   # Single word
                r'--oem 3 --psm 13',  # Raw line
                r'--oem 3 --psm 11',  # Sparse text
            ]
    
    @classmethod
    def from_environment(cls) -> 'OCRConfig':
        """Create OCR config from environment variables"""
        return cls(
            enabled=os.getenv('OCR_ENABLED', 'true').lower() == 'true',
            confidence_threshold=float(os.getenv('OCR_CONFIDENCE_THRESHOLD', '0.3')),
            enhance_contrast=os.getenv('OCR_ENHANCE_CONTRAST', 'true').lower() == 'true',
            enhance_sharpness=os.getenv('OCR_ENHANCE_SHARPNESS', 'true').lower() == 'true',
            min_image_size=int(os.getenv('OCR_MIN_IMAGE_SIZE', '300')),
            languages=os.getenv('OCR_LANGUAGES', 'eng'),
            include_confidence_in_output=os.getenv('OCR_INCLUDE_CONFIDENCE', 'false').lower() == 'true',
            mark_image_text=os.getenv('OCR_MARK_IMAGE_TEXT', 'true').lower() == 'true'
        )
    
    def get_tesseract_config_with_language(self, config: str) -> str:
        """Add language parameter to tesseract config"""
        if self.languages and self.languages != 'eng':
            return f"{config} -l {self.languages}"
        return config
    
    def should_process_image(self, image_width: int, image_height: int) -> bool:
        """Check if image should be processed based on size"""
        return (self.enabled and 
                image_width >= self.min_image_size and 
                image_height >= self.min_image_size)
    
    def format_extracted_text(self, text: str, confidence: float, page_num: Optional[int] = None) -> str:
        """Format extracted text according to configuration"""
        if not text.strip():
            return ""
        
        formatted_text = text.strip()
        
        if self.mark_image_text:
            if page_num is not None:
                prefix = f"[IMAGE TEXT FROM PAGE {page_num}]"
            else:
                prefix = "[IMAGE TEXT]"
            
            if self.include_confidence_in_output:
                prefix += f" (confidence: {confidence:.1%})"
            
            formatted_text = f"{prefix}: {formatted_text}"
        
        return formatted_text

# Global OCR configuration instance
ocr_config = OCRConfig.from_environment()

def get_ocr_config() -> OCRConfig:
    """Get the global OCR configuration"""
    return ocr_config

def update_ocr_config(**kwargs) -> None:
    """Update OCR configuration at runtime"""
    global ocr_config
    for key, value in kwargs.items():
        if hasattr(ocr_config, key):
            setattr(ocr_config, key, value)
        else:
            logger.warning(f"Unknown OCR config parameter: {key}")

def is_ocr_available() -> bool:
    """Check if OCR is available and properly configured"""
    try:
        import pytesseract
        from PIL import Image
        
        # Try a simple OCR test
        test_image = Image.new('RGB', (100, 50), color='white')
        pytesseract.image_to_string(test_image)
        return True
        
    except Exception as e:
        logger.warning(f"OCR not available: {str(e)}")
        return False