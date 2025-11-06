#!/usr/bin/env python3
"""
Tabular Data Processing Service
Integrated utility for handling CSV, Excel, TSV files within the main service
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple
import io
import logging

logger = logging.getLogger(__name__)

class TabularProcessor:
    """Utility class for tabular data operations"""
    
    @staticmethod
    def detect_file_type(filename: str, content: bytes) -> Optional[str]:
        """Detect tabular file type"""
        if not filename:
            return None
            
        filename_lower = filename.lower()
        
        if filename_lower.endswith(('.xlsx', '.xls')):
            return 'excel'
        elif filename_lower.endswith('.tsv'):
            return 'tsv'
        elif filename_lower.endswith('.csv'):
            return 'csv'
        
        # Content-based detection for CSV-like files (only for files without clear extensions)
        # Skip content-based detection for known binary formats and code files
        if filename_lower.endswith(('.docx', '.doc', '.pdf', '.xlsx', '.xls', '.pptx', '.ppt',
                                   '.tsx', '.jsx', '.ts', '.js', '.css', '.scss', '.less',
                                   '.html', '.htm', '.xml', '.json', '.yaml', '.yml',
                                   '.py', '.java', '.cpp', '.c', '.h', '.php', '.rb',
                                   '.go', '.rs', '.swift', '.kt', '.scala', '.sh', '.bat')):
            return None
            
        try:
            # Only try content-based detection if it looks like it could be text
            text_content = content.decode('utf-8')[:1024]
            
            # More restrictive content-based detection
            comma_count = text_content.count(',')
            semicolon_count = text_content.count(';')
            tab_count = text_content.count('\t')
            newline_count = text_content.count('\n')
            
            # Only detect as CSV if it has VERY clear tabular structure AND consistent formatting
            has_tabular_structure = (comma_count > 2 or semicolon_count > 2 or tab_count > 2) and newline_count > 1
            has_binary_markers = any(ord(c) < 32 and c not in '\t\n\r' for c in text_content[:100])
            
            # Additional checks for CSV-like structure
            lines = text_content.split('\n')[:10]  # Check first 10 lines
            if len(lines) < 2:
                return None
                
            # Check if lines have consistent separator counts (indicating tabular data)
            separator_counts = []
            for line in lines:
                if line.strip():  # Skip empty lines
                    count = max(line.count(','), line.count(';'), line.count('\t'))
                    separator_counts.append(count)
            
            # Only consider it CSV if most lines have similar separator counts
            if len(separator_counts) >= 2:
                avg_count = sum(separator_counts) / len(separator_counts)
                consistent_structure = all(abs(count - avg_count) <= 1 for count in separator_counts)
                
                if has_tabular_structure and not has_binary_markers and consistent_structure and avg_count >= 2:
                    return 'csv'
        except UnicodeDecodeError:
            # If it can't be decoded as UTF-8, it's definitely not a CSV
            pass
        except:
            pass
            
        return None
    
    @staticmethod
    def load_dataframe(content: bytes, file_type: str, filename: str = None) -> pd.DataFrame:
        """Load content into pandas DataFrame based on file type"""
        
        if file_type == 'excel':
            return pd.read_excel(io.BytesIO(content))
            
        elif file_type == 'tsv':
            text_content = content.decode('utf-8')
            return pd.read_csv(io.StringIO(text_content), sep='\t')
            
        elif file_type == 'csv':
            text_content = content.decode('utf-8')
            
            # Auto-detect delimiter
            delimiter = ','
            if text_content.count(';') > text_content.count(','):
                delimiter = ';'
            elif text_content.count('\t') > text_content.count(','):
                delimiter = '\t'
            elif text_content.count('|') > text_content.count(','):
                delimiter = '|'
            
            # Try parsing with robust error handling
            try:
                # First attempt: strict parsing
                return pd.read_csv(io.StringIO(text_content), sep=delimiter)
            except Exception as e:
                logger.warning(f"CSV parsing failed with strict mode: {e}")
                # Second attempt: flexible parsing
                try:
                    return pd.read_csv(
                        io.StringIO(text_content), 
                        sep=delimiter,
                        skipinitialspace=True,  # Skip spaces after delimiter
                        skip_blank_lines=True,  # Skip empty lines
                        quoting=1               # Quote minimal
                    )
                except Exception as e2:
                    logger.warning(f"CSV parsing failed with flexible mode: {e2}")
                    # Third attempt: most permissive parsing
                    return pd.read_csv(
                        io.StringIO(text_content), 
                        sep=delimiter,
                        quoting=3,              # No quoting
                        skipinitialspace=True,
                        skip_blank_lines=True,
                        engine='python'         # Use Python engine for more flexibility
                    )
        
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
    
    @staticmethod
    def create_table_data(df: pd.DataFrame, file_type: str, filename: str, max_rows: int = None) -> Dict:
        """Create standardized table data structure with size limits for large files"""
        # Get configuration for large file handling
        if max_rows is None:
            from src.config.app_config import config
            max_rows = config.large_file.max_storage_rows
        
        # Replace NaN values with None for JSON serialization
        df_clean = df.replace({np.nan: None})
        
        # For large datasets, only store a sample to prevent browser crashes
        if len(df) > max_rows:
            # Store only a sample of the data + metadata
            sample_df = df_clean.head(max_rows)
            data_records = sample_df.to_dict('records')
            is_truncated = True
            logger.warning(f"Large dataset detected ({len(df)} rows). Storing only first {max_rows} rows to prevent memory issues.")
        else:
            # Store full dataset for smaller files
            data_records = df_clean.to_dict('records')
            is_truncated = False
        
        return {
            "table_index": 0,
            "page_number": 1,
            "title": f"{file_type.upper()} Data: {filename}",
            "headers": list(df.columns),  # Always include headers
            "data": data_records,  # Limited dataset to prevent crashes
            "row_count": len(df),  # Full count
            "column_count": len(df.columns),
            "sample_size": len(data_records),  # Actual stored rows
            "is_truncated": is_truncated,  # Flag indicating if data was truncated
            "table_type": f"{file_type}_data",
            "confidence_score": 1.0,
            "extraction_method": f"{file_type}_parser",
            "data_quality_score": 1.0,
            "column_types": {col: str(df[col].dtype) for col in df.columns}
        }
    
    @staticmethod
    def get_preview_data(df: pd.DataFrame, rows: int = None) -> List[Dict]:
        """Get preview data as list of records with configurable size limits"""
        # Get configuration for preview size
        if rows is None:
            from src.config.app_config import config
            rows = config.large_file.max_preview_rows
        
        # Limit preview size to prevent browser crashes
        preview_rows = min(rows, len(df))
        
        # Replace NaN values with None for JSON serialization
        df_preview = df.head(preview_rows).replace({np.nan: None})
        return df_preview.to_dict('records')
    
    @staticmethod
    def analyze_data_quality(df: pd.DataFrame) -> Dict:
        """Analyze data quality metrics"""
        # Convert numpy types to Python types for JSON serialization
        null_counts = df.isnull().sum()
        data_types = df.dtypes
        
        return {
            "null_counts": {str(k): int(v) for k, v in null_counts.items()},
            "duplicate_rows": int(df.duplicated().sum()),
            "memory_usage_mb": round(df.memory_usage(deep=True).sum() / 1024**2, 2),
            "data_types": {str(k): str(v) for k, v in data_types.items()}
        }