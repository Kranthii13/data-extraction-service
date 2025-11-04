"""
Robust OCR Implementation
Handles errors gracefully and processes images reliably
"""

import logging
import io
import tempfile
import os
from typing import Tuple, Optional
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract

logger = logging.getLogger(__name__)

class RobustOCR:
    """Robust OCR processor with error handling and image optimization"""
    
    def __init__(self, confidence_threshold: float = 0.1, min_image_size: int = 50):
        self.confidence_threshold = confidence_threshold
        self.min_image_size = min_image_size
        self.max_image_size = 2000  # Reduced for faster processing
        
    def extract_text_from_image(self, image_data: bytes, page_num: Optional[int] = None) -> Tuple[str, float]:
        """
        Extract text from image data with robust error handling
        
        Args:
            image_data: Raw image bytes
            page_num: Page number for logging
            
        Returns:
            Tuple of (extracted_text, confidence_score)
        """
        try:
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_data))
            return self._process_image(image, page_num)
            
        except Exception as e:
            logger.warning(f"Failed to process image from bytes: {str(e)}")
            return "", 0.0
    
    def extract_text_from_pil_image(self, image: Image.Image, page_num: Optional[int] = None) -> Tuple[str, float]:
        """
        Extract text from PIL Image with robust error handling
        
        Args:
            image: PIL Image object
            page_num: Page number for logging
            
        Returns:
            Tuple of (extracted_text, confidence_score)
        """
        try:
            return self._process_image(image, page_num)
        except Exception as e:
            logger.warning(f"Failed to process PIL image: {str(e)}")
            return "", 0.0
    
    def _process_image(self, image: Image.Image, page_num: Optional[int] = None) -> Tuple[str, float]:
        """
        Internal method to process image with multiple strategies
        """
        try:
            # Basic validation
            if not self._is_valid_image(image):
                return "", 0.0
            
            # Try only the most effective strategies for speed
            strategies = [
                self._strategy_direct,
                self._strategy_enhanced
            ]
            
            best_text = ""
            best_confidence = 0.0
            
            for strategy in strategies:
                try:
                    text, confidence = strategy(image)
                    
                    # Use result if it's better than previous attempts
                    if confidence > best_confidence and len(text.strip()) > 0:
                        best_text = text
                        best_confidence = confidence
                        
                        # If we get decent confidence, stop trying other strategies
                        if confidence > 0.5:
                            break
                            
                except Exception as e:
                    logger.debug(f"OCR strategy failed: {str(e)}")
                    continue
            
            # Apply confidence threshold
            if best_confidence >= self.confidence_threshold:
                page_info = f" on page {page_num}" if page_num else ""
                logger.info(f"OCR extracted text{page_info}: confidence {best_confidence:.2%}")
                return best_text.strip(), best_confidence
            else:
                logger.debug(f"OCR text below confidence threshold: {best_confidence:.2%} < {self.confidence_threshold:.2%}")
                return "", 0.0
                
        except Exception as e:
            logger.error(f"OCR processing failed: {str(e)}")
            return "", 0.0
    
    def _is_valid_image(self, image: Image.Image) -> bool:
        """Check if image is valid for OCR processing"""
        try:
            width, height = image.size
            
            # Check minimum size
            if width < self.min_image_size or height < self.min_image_size:
                logger.debug(f"Image too small: {width}x{height} < {self.min_image_size}")
                return False
            
            # Check maximum size (prevent memory issues)
            if width > self.max_image_size or height > self.max_image_size:
                logger.debug(f"Image too large: {width}x{height} > {self.max_image_size}")
                return False
            
            # Check if image has content
            if image.mode not in ['RGB', 'RGBA', 'L', 'P']:
                logger.debug(f"Unsupported image mode: {image.mode}")
                return False
                
            return True
            
        except Exception as e:
            logger.debug(f"Image validation failed: {str(e)}")
            return False
    
    def _strategy_direct(self, image: Image.Image) -> Tuple[str, float]:
        """Direct OCR without preprocessing"""
        return self._perform_ocr(image, "direct")
    
    def _strategy_enhanced(self, image: Image.Image) -> Tuple[str, float]:
        """OCR with optimized enhancement for scanned documents"""
        try:
            # Convert to grayscale for better OCR on scanned docs
            if image.mode != 'L':
                image = image.convert('L')
            
            # Resize for optimal OCR (aim for 300 DPI equivalent)
            width, height = image.size
            if width < 600 or height < 600:
                scale = max(600 / width, 600 / height)
                new_size = (int(width * scale), int(height * scale))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            
            # Enhance contrast more aggressively for scanned docs
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(2.0)
            
            # Enhance sharpness
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(1.5)
            
            return self._perform_ocr(image, "enhanced")
            
        except Exception as e:
            logger.debug(f"Enhanced strategy failed: {str(e)}")
            return "", 0.0
    
    def _strategy_grayscale_enhanced(self, image: Image.Image) -> Tuple[str, float]:
        """OCR with grayscale conversion and enhancement"""
        try:
            # Convert to grayscale
            if image.mode != 'L':
                image = image.convert('L')
            
            # Resize if needed
            width, height = image.size
            if width < 400 or height < 400:
                scale = max(400 / width, 400 / height)
                new_size = (int(width * scale), int(height * scale))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            
            # Enhance contrast more aggressively
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(2.0)
            
            return self._perform_ocr(image, "grayscale")
            
        except Exception as e:
            logger.debug(f"Grayscale strategy failed: {str(e)}")
            return "", 0.0
    
    def _strategy_high_contrast(self, image: Image.Image) -> Tuple[str, float]:
        """OCR with high contrast processing"""
        try:
            # Convert to grayscale
            if image.mode != 'L':
                image = image.convert('L')
            
            # Apply high contrast
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(3.0)
            
            # Apply brightness adjustment
            enhancer = ImageEnhance.Brightness(image)
            image = enhancer.enhance(1.2)
            
            return self._perform_ocr(image, "high_contrast")
            
        except Exception as e:
            logger.debug(f"High contrast strategy failed: {str(e)}")
            return "", 0.0
    
    def _strategy_denoised(self, image: Image.Image) -> Tuple[str, float]:
        """OCR with noise reduction"""
        try:
            # Convert to grayscale
            if image.mode != 'L':
                image = image.convert('L')
            
            # Apply median filter to reduce noise
            image = image.filter(ImageFilter.MedianFilter(size=3))
            
            # Enhance contrast
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.8)
            
            return self._perform_ocr(image, "denoised")
            
        except Exception as e:
            logger.debug(f"Denoised strategy failed: {str(e)}")
            return "", 0.0
    
    def _perform_ocr(self, image: Image.Image, strategy_name: str) -> Tuple[str, float]:
        """
        Perform OCR with optimized single configuration for speed
        """
        # Use only the fastest, most reliable configuration
        configs = [
            r'--oem 3 --psm 6',   # Uniform block of text - fastest and most reliable
        ]
        
        best_text = ""
        best_confidence = 0.0
        
        for config in configs:
            try:
                # Get OCR data with confidence scores
                ocr_data = pytesseract.image_to_data(
                    image, 
                    config=config, 
                    output_type=pytesseract.Output.DICT
                )
                
                # Extract text and calculate confidence
                text_parts = []
                confidences = []
                
                for i, word in enumerate(ocr_data['text']):
                    if word.strip():
                        text_parts.append(word)
                        conf = int(ocr_data['conf'][i])
                        if conf > 0:  # Only include positive confidence scores
                            confidences.append(conf)
                
                if text_parts and confidences:
                    extracted_text = ' '.join(text_parts)
                    avg_confidence = sum(confidences) / len(confidences) / 100.0
                    
                    # Use this result if it's better
                    if avg_confidence > best_confidence:
                        best_text = extracted_text
                        best_confidence = avg_confidence
                
            except Exception as e:
                logger.debug(f"OCR config '{config}' failed: {str(e)}")
                continue
        
        logger.debug(f"OCR strategy '{strategy_name}': '{best_text[:50]}...' (confidence: {best_confidence:.2%})")
        return best_text, best_confidence
    
    def save_debug_image(self, image: Image.Image, filename: str):
        """Save image for debugging purposes"""
        try:
            debug_dir = "debug_images"
            os.makedirs(debug_dir, exist_ok=True)
            image.save(os.path.join(debug_dir, filename))
            logger.debug(f"Saved debug image: {filename}")
        except Exception as e:
            logger.debug(f"Failed to save debug image: {str(e)}")

# Global OCR instance
_ocr_instance = None

def get_ocr_processor() -> RobustOCR:
    """Get global OCR processor instance"""
    global _ocr_instance
    if _ocr_instance is None:
        from .ocr_config import get_ocr_config
        config = get_ocr_config()
        _ocr_instance = RobustOCR(
            confidence_threshold=config.confidence_threshold,
            min_image_size=config.min_image_size
        )
    return _ocr_instance