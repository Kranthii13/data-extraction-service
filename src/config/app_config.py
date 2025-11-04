#!/usr/bin/env python3
"""
Application Configuration
Centralized configuration management for the data extraction service
"""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class DatabaseConfig:
    """Database configuration settings"""
    host: str = os.getenv('POSTGRES_HOST', 'localhost')
    port: int = int(os.getenv('POSTGRES_PORT', 5432))
    database: str = os.getenv('POSTGRES_DB', 'filedb')
    username: str = os.getenv('POSTGRES_USER', 'postgres')
    password: str = os.getenv('POSTGRES_PASSWORD', 'postgres')
    
    @property
    def url(self) -> str:
        """Get database connection URL"""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

@dataclass
class OCRConfig:
    """OCR processing configuration"""
    enabled: bool = os.getenv('OCR_ENABLED', 'true').lower() == 'true'
    confidence_threshold: float = float(os.getenv('OCR_CONFIDENCE_THRESHOLD', '0.1'))
    enhance_contrast: bool = os.getenv('OCR_ENHANCE_CONTRAST', 'true').lower() == 'true'
    enhance_sharpness: bool = os.getenv('OCR_ENHANCE_SHARPNESS', 'true').lower() == 'true'
    min_image_size: int = int(os.getenv('OCR_MIN_IMAGE_SIZE', '300'))
    languages: str = os.getenv('OCR_LANGUAGES', 'eng')

@dataclass
class TableExtractionConfig:
    """Table extraction configuration"""
    enabled: bool = True
    max_file_size_mb: int = int(os.getenv('MAX_FILE_SIZE_FOR_TABLES', '10485760')) // (1024 * 1024)  # Convert to MB
    skip_large_files: bool = os.getenv('SKIP_TABLE_EXTRACTION_FOR_LARGE_FILES', 'true').lower() == 'true'
    detection_methods: list = None
    
    def __post_init__(self):
        if self.detection_methods is None:
            self.detection_methods = ['pymupdf', 'ocr', 'text_pattern']

@dataclass
class AppConfig:
    """Main application configuration"""
    host: str = os.getenv('HOST', '0.0.0.0')
    port: int = int(os.getenv('PORT', 8000))
    reload: bool = os.getenv('RELOAD', 'false').lower() == 'true'
    log_level: str = os.getenv('LOG_LEVEL', 'info')
    log_to_file: bool = os.getenv('LOG_TO_FILE', 'false').lower() == 'true'
    fast_mode: bool = os.getenv('FAST_MODE', 'true').lower() == 'true'

@dataclass
class ServiceConfig:
    """Complete service configuration"""
    app: AppConfig
    database: DatabaseConfig
    ocr: OCRConfig
    table_extraction: TableExtractionConfig
    
    @classmethod
    def load(cls) -> 'ServiceConfig':
        """Load configuration from environment"""
        return cls(
            app=AppConfig(),
            database=DatabaseConfig(),
            ocr=OCRConfig(),
            table_extraction=TableExtractionConfig()
        )

# Global configuration instance
config = ServiceConfig.load()