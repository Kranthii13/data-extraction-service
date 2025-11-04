# src/infrastructure/api.py
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import os
import uuid
import json
import logging
from datetime import datetime
from enum import Enum

from src.core.models import Document, ExtractedData
from src.services.ports import IExtractionService
from src.adapters.dependencies import get_extraction_service, get_db

logger = logging.getLogger(__name__)

# Check if production dependencies are available
USE_CELERY = False
try:
    import celery
    import redis
    
    # Test Redis connection
    redis_client = redis.Redis(
        host=os.getenv('REDIS_HOST', 'localhost'),
        port=int(os.getenv('REDIS_PORT', 6379)),
        db=int(os.getenv('REDIS_DB', 0)),
        decode_responses=True
    )
    redis_client.ping()
    
    # Setup Celery
    celery_app = celery.Celery(
        'document_processor',
        broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
        backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
    )
    
    @celery_app.task
    def process_document_task(document_data: dict) -> dict:
        """Celery task for document processing."""
        import base64
        from src.core.models import Document
        from src.adapters.dependencies import get_extraction_service, SessionLocal
        
        content = base64.b64decode(document_data['content'])
        document = Document(content=content, filename=document_data['filename'])
        
        db = SessionLocal()
        try:
            service = get_extraction_service(db)
            result = service.extract_from_document(document)
            return {
                'id': getattr(result, 'id', None),
                'filename': document_data['filename'],
                'page_count': result.page_count,
                'processing_method': result.processing_method,
                'has_ocr_content': result.has_ocr_content,
                'text_preview': result.full_text[:200] + "..." if len(result.full_text) > 200 else result.full_text
            }
        finally:
            db.close()
    
    USE_CELERY = True
    logger.info("Using Celery + Redis for task processing")
    
except Exception as e:
    logger.info(f"Using BackgroundTasks for task processing: {e}")
    # Simple task store for development
    task_store: Dict[str, Dict[str, Any]] = {}

class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

app = FastAPI(
    title="Data Extraction Service",
    description="Document processing with async support",
    version="1.0.0"
)

# Task management functions
def store_task_status(task_id: str, status: dict):
    """Store task status."""
    if USE_CELERY:
        redis_client.setex(f"task:{task_id}", 3600, json.dumps(status))
    else:
        task_store[task_id] = status

def get_task_status(task_id: str) -> Optional[dict]:
    """Get task status."""
    if USE_CELERY:
        data = redis_client.get(f"task:{task_id}")
        return json.loads(data) if data else None
    else:
        return task_store.get(task_id)

def update_task_status(task_id: str, updates: dict):
    """Update task status."""
    if USE_CELERY:
        current = get_task_status(task_id) or {}
        current.update(updates)
        redis_client.setex(f"task:{task_id}", 3600, json.dumps(current))
    else:
        if task_id in task_store:
            task_store[task_id].update(updates)

# Background processing for development
async def process_document_background(task_id: str, document: Document, db: Session):
    """Process document in background."""
    try:
        update_task_status(task_id, {"status": TaskStatus.PROCESSING})
        
        service = get_extraction_service(db)
        result = service.extract_from_document(document)
        
        update_task_status(task_id, {
            "status": TaskStatus.COMPLETED,
            "result": {
                "id": getattr(result, 'id', None),
                "filename": document.filename,
                "page_count": result.page_count,
                "processing_method": result.processing_method,
                "has_ocr_content": result.has_ocr_content,
                "text_preview": result.full_text[:200] + "..." if len(result.full_text) > 200 else result.full_text
            }
        })
        
    except Exception as e:
        logger.error(f"Background processing failed: {e}")
        update_task_status(task_id, {
            "status": TaskStatus.FAILED,
            "error": str(e)
        })

# API Endpoints
@app.post("/extract/")
async def extract_sync(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Process document synchronously with performance tracking."""
    import time
    start_time = time.time()
    
    content = await file.read()
    document = Document(content=content, filename=file.filename)
    
    service = get_extraction_service(db)
    
    # Get the action info by checking if document exists first
    import hashlib
    from src.adapters.database.models import DocumentRecord
    
    file_hash = hashlib.sha256(content).hexdigest()
    existing = db.query(DocumentRecord).filter(DocumentRecord.file_hash == file_hash).first()
    action = "updated" if existing else "created"
    
    # Process the document
    result = service.extract_from_document(document)
    
    # Calculate processing time
    processing_time = round((time.time() - start_time) * 1000)  # milliseconds
    
    # Convert tables to serializable format
    tables_data = []
    if result.tables:
        for table in result.tables:
            table_dict = {
                "table_index": table.table_index,
                "page_number": table.page_number,
                "title": table.title,
                "context_before": table.context_before,
                "context_after": table.context_after,
                "section_heading": table.section_heading,
                "headers": table.headers,
                "rows": table.rows,
                "row_count": table.row_count,
                "column_count": table.column_count,
                "table_type": table.table_type,
                "confidence_score": table.confidence_score,
                "extraction_method": table.extraction_method
            }
            tables_data.append(table_dict)
    
    # Add action information to response
    response_data = {
        "id": result.id,
        "filename": result.filename,
        "full_text": result.full_text,
        "page_count": result.page_count,
        "has_ocr_content": result.has_ocr_content,
        "processing_method": result.processing_method,
        "table_count": result.table_count,
        "tables": tables_data,
        "action": action,
        "processing_time_ms": processing_time,
        "file_size_bytes": len(content)
    }
    
    return response_data

@app.post("/extract/async/")
async def extract_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Process document asynchronously."""
    content = await file.read()
    document = Document(content=content, filename=file.filename)
    task_id = str(uuid.uuid4())
    
    # Store initial task status
    store_task_status(task_id, {
        "task_id": task_id,
        "status": TaskStatus.PENDING,
        "filename": file.filename,
        "created_at": datetime.now().isoformat()
    })
    
    if USE_CELERY:
        # Use Celery for production
        import base64
        task_data = {
            'content': base64.b64encode(content).decode('utf-8'),
            'filename': file.filename
        }
        celery_task = process_document_task.delay(task_data)
        update_task_status(task_id, {"celery_task_id": celery_task.id})
    else:
        # Use BackgroundTasks for development
        background_tasks.add_task(process_document_background, task_id, document, db)
    
    return {
        "task_id": task_id,
        "status": "pending"
    }

@app.get("/extract/status/{task_id}")
async def get_status(task_id: str):
    """Get task status."""
    status = get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check Celery status if using Celery
    if USE_CELERY and 'celery_task_id' in status:
        celery_task = celery_app.AsyncResult(status['celery_task_id'])
        if celery_task.state == 'SUCCESS':
            update_task_status(task_id, {
                "status": TaskStatus.COMPLETED,
                "result": celery_task.result
            })
            status = get_task_status(task_id)
        elif celery_task.state == 'FAILURE':
            update_task_status(task_id, {
                "status": TaskStatus.FAILED,
                "error": str(celery_task.info)
            })
            status = get_task_status(task_id)
    
    return status

@app.get("/documents/{document_id}", response_model=ExtractedData)
async def get_document(document_id: int, db: Session = Depends(get_db)):
    """Get document by ID."""
    service = get_extraction_service(db)
    document = service.get_document_by_id(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document

@app.get("/documents/", response_model=List[ExtractedData])
async def get_documents(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get all documents."""
    service = get_extraction_service(db)
    return service.get_all_documents(limit=limit, offset=offset)

@app.get("/search/", response_model=List[ExtractedData])
async def search_documents(
    q: str = Query(..., min_length=1),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """Search documents."""
    service = get_extraction_service(db)
    return service.search_documents(search_term=q, limit=limit)

@app.get("/documents/{document_id}/tables")
async def get_document_tables(document_id: int, db: Session = Depends(get_db)):
    """Get all tables from a specific document."""
    service = get_extraction_service(db)
    document = service.get_document_by_id(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Enhance response with contextual information
    tables_with_context = []
    for table in document.tables:
        table_info = {
            "table_index": table.table_index,
            "page_number": table.page_number,
            "title": table.title,
            "context_before": table.context_before,
            "context_after": table.context_after,
            "section_heading": table.section_heading,
            "table_type": table.table_type,
            "confidence_score": table.confidence_score,
            "headers": table.headers,
            "row_count": table.row_count,
            "column_count": table.column_count,
            "rows": table.rows[:5] if table.rows else [],  # Show first 5 rows as preview
            "total_rows": len(table.rows) if table.rows else 0
        }
        tables_with_context.append(table_info)
    
    return {
        "document_id": document_id,
        "filename": document.filename,
        "table_count": document.table_count,
        "tables": tables_with_context
    }

@app.get("/documents/{document_id}/tables/{table_index}")
async def get_document_table(
    document_id: int, 
    table_index: int, 
    format: str = Query("json", regex="^(json|html|markdown|context)$"),
    db: Session = Depends(get_db)
):
    """Get a specific table from a document with contextual information."""
    from src.adapters.database.models import DocumentRecord
    
    # Get document with tables
    document = db.query(DocumentRecord).filter(DocumentRecord.id == document_id).first()
    if not document or not document.tables_data:
        raise HTTPException(status_code=404, detail="Document or table not found")
    
    # Find the specific table
    table_data = None
    for table in document.tables_data:
        if table.get("table_index") == table_index:
            table_data = table
            break
    
    if not table_data:
        raise HTTPException(status_code=404, detail="Table not found")
    
    if format == "html":
        return {"table_html": table_data.get("table_html")}
    elif format == "markdown":
        return {"table_markdown": table_data.get("table_markdown")}
    elif format == "context":
        return {
            "table_index": table_data.get("table_index"),
            "page_number": table_data.get("page_number"),
            "title": table_data.get("title"),
            "context_before": table_data.get("context_before"),
            "context_after": table_data.get("context_after"),
            "section_heading": table_data.get("section_heading"),
            "table_type": table_data.get("table_type"),
            "confidence_score": table_data.get("confidence_score"),
            "headers": table_data.get("headers"),
            "rows": table_data.get("rows"),
            "row_count": table_data.get("row_count"),
            "column_count": table_data.get("column_count")
        }
    else:  # json (basic)
        return {
            "table_index": table_data.get("table_index"),
            "page_number": table_data.get("page_number"),
            "headers": table_data.get("headers"),
            "rows": table_data.get("rows"),
            "row_count": table_data.get("row_count"),
            "column_count": table_data.get("column_count")
        }

@app.get("/tables/search")
async def search_tables(
    q: str = Query(..., min_length=1),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """Search within table content using PostgreSQL JSON queries."""
    from src.adapters.database.models import DocumentRecord
    from sqlalchemy import text
    
    # Search in tables_data JSON using PostgreSQL JSON operators
    query = text("""
        SELECT d.id, d.filename, d.tables_data, d.table_count
        FROM documents d
        WHERE d.tables_data IS NOT NULL 
        AND d.tables_data::text ILIKE :search_term
        LIMIT :limit
    """)
    
    results = db.execute(query, {
        "search_term": f"%{q}%",
        "limit": limit
    }).fetchall()
    
    # Process results to extract matching tables
    table_results = []
    for row in results:
        if row.tables_data:
            for table in row.tables_data:
                # Check if this table contains the search term
                table_text = table.get("table_text", "")
                if q.lower() in table_text.lower():
                    table_results.append({
                        "document_id": row.id,
                        "filename": row.filename,
                        "table_index": table.get("table_index"),
                        "page_number": table.get("page_number"),
                        "headers": table.get("headers"),
                        "row_count": table.get("row_count"),
                        "column_count": table.get("column_count"),
                        "table_text": table_text[:200] + "..." if len(table_text) > 200 else table_text
                    })
    
    return {
        "query": q,
        "total_results": len(table_results),
        "tables": table_results[:limit]
    }



@app.get("/tables/by-type/{table_type}")
async def get_tables_by_type(
    table_type: str,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """Get all tables of a specific type across all documents."""
    from src.adapters.database.models import DocumentRecord
    from sqlalchemy import text
    
    # Search for tables of specific type using PostgreSQL JSON queries
    query = text("""
        SELECT d.id, d.filename, d.tables_data
        FROM documents d
        WHERE d.tables_data IS NOT NULL 
        AND d.tables_data::text ILIKE :table_type_pattern
        LIMIT :limit
    """)
    
    results = db.execute(query, {
        "table_type_pattern": f'%"table_type": "{table_type}"%',
        "limit": limit
    }).fetchall()
    
    # Extract matching tables
    matching_tables = []
    for row in results:
        if row.tables_data:
            for table in row.tables_data:
                if table.get("table_type") == table_type:
                    matching_tables.append({
                        "document_id": row.id,
                        "filename": row.filename,
                        "table_index": table.get("table_index"),
                        "title": table.get("title"),
                        "section_heading": table.get("section_heading"),
                        "page_number": table.get("page_number"),
                        "headers": table.get("headers"),
                        "row_count": table.get("row_count"),
                        "column_count": table.get("column_count"),
                        "confidence_score": table.get("confidence_score")
                    })
    
    return {
        "table_type": table_type,
        "total_results": len(matching_tables),
        "tables": matching_tables
    }

@app.get("/documents/{document_id}/tables/quality")
async def get_table_quality_metrics(document_id: int, db: Session = Depends(get_db)):
    """Get quality metrics for all tables in a document."""
    service = get_extraction_service(db)
    document = service.get_document_by_id(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    quality_metrics = {
        "document_id": document_id,
        "filename": document.filename,
        "total_tables": document.table_count,
        "tables": []
    }
    
    total_quality = 0
    total_confidence = 0
    
    for table in document.tables:
        table_metrics = {
            "table_index": table.table_index,
            "extraction_method": table.extraction_method,
            "confidence_score": table.confidence_score,
            "data_quality_score": table.data_quality_score,
            "column_types": table.column_types,
            "processing_time_ms": table.processing_time_ms,
            "has_errors": bool(table.extraction_errors),
            "errors": table.extraction_errors or []
        }
        quality_metrics["tables"].append(table_metrics)
        
        if table.data_quality_score:
            total_quality += table.data_quality_score
        if table.confidence_score:
            total_confidence += table.confidence_score
    
    # Calculate overall metrics
    if document.table_count > 0:
        quality_metrics["average_quality_score"] = round(total_quality / document.table_count, 2)
        quality_metrics["average_confidence_score"] = round(total_confidence / document.table_count, 2)
    else:
        quality_metrics["average_quality_score"] = 0
        quality_metrics["average_confidence_score"] = 0
    
    return quality_metrics

@app.get("/tables/export/{document_id}/{table_index}")
async def export_table(
    document_id: int,
    table_index: int,
    format: str = Query("csv", regex="^(csv|excel|json)$"),
    db: Session = Depends(get_db)
):
    """Export a specific table in various formats."""
    from src.adapters.database.models import DocumentRecord
    from fastapi.responses import Response
    
    # Get document with tables
    document = db.query(DocumentRecord).filter(DocumentRecord.id == document_id).first()
    if not document or not document.tables_data:
        raise HTTPException(status_code=404, detail="Document or table not found")
    
    # Find the specific table
    table_data = None
    for table in document.tables_data:
        if table.get("table_index") == table_index:
            table_data = table
            break
    
    if not table_data:
        raise HTTPException(status_code=404, detail="Table not found")
    
    filename = f"table_{document_id}_{table_index}"
    
    if format == "csv":
        content = table_data.get("table_csv", "")
        media_type = "text/csv"
        filename += ".csv"
    elif format == "excel":
        # Create Excel file (would need openpyxl library)
        content = table_data.get("table_csv", "")  # Fallback to CSV for now
        media_type = "application/vnd.ms-excel"
        filename += ".xlsx"
    else:  # json
        import json
        table_json = {
            "headers": table_data.get("headers"),
            "rows": table_data.get("rows"),
            "metadata": {
                "table_type": table_data.get("table_type"),
                "column_types": table_data.get("column_types"),
                "confidence_score": table_data.get("confidence_score")
            }
        }
        content = json.dumps(table_json, indent=2)
        media_type = "application/json"
        filename += ".json"
    
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/tables/stats")
async def get_table_statistics(db: Session = Depends(get_db)):
    """Get comprehensive table extraction statistics."""
    from src.adapters.database.models import DocumentRecord
    from sqlalchemy import text, func
    
    # Basic document and table statistics
    doc_stats = db.query(
        func.count(DocumentRecord.id).label('total_documents'),
        func.sum(DocumentRecord.table_count).label('total_tables'),
        func.avg(DocumentRecord.table_count).label('avg_tables_per_doc'),
        func.count().filter(DocumentRecord.table_count > 0).label('docs_with_tables')
    ).first()
    
    # Table type distribution
    table_type_stats = db.execute(text("""
        SELECT 
            json_array_elements(tables_data)->>'table_type' as table_type,
            COUNT(*) as count
        FROM documents 
        WHERE tables_data IS NOT NULL
        GROUP BY json_array_elements(tables_data)->>'table_type'
        ORDER BY count DESC
    """)).fetchall()
    
    # Extraction method statistics
    extraction_method_stats = db.execute(text("""
        SELECT 
            json_array_elements(tables_data)->>'extraction_method' as method,
            COUNT(*) as count,
            AVG((json_array_elements(tables_data)->>'confidence_score')::float) as avg_confidence,
            AVG((json_array_elements(tables_data)->>'data_quality_score')::float) as avg_quality
        FROM documents 
        WHERE tables_data IS NOT NULL
        GROUP BY json_array_elements(tables_data)->>'extraction_method'
    """)).fetchall()
    
    # Data quality distribution
    quality_stats = db.execute(text("""
        SELECT 
            CASE 
                WHEN (json_array_elements(tables_data)->>'data_quality_score')::float >= 0.8 THEN 'high'
                WHEN (json_array_elements(tables_data)->>'data_quality_score')::float >= 0.6 THEN 'medium'
                ELSE 'low'
            END as quality_level,
            COUNT(*) as count
        FROM documents 
        WHERE tables_data IS NOT NULL
        GROUP BY quality_level
    """)).fetchall()
    
    return {
        "document_statistics": {
            "total_documents": doc_stats.total_documents or 0,
            "documents_with_tables": doc_stats.docs_with_tables or 0,
            "total_tables_extracted": doc_stats.total_tables or 0,
            "average_tables_per_document": round(float(doc_stats.avg_tables_per_doc or 0), 2)
        },
        "table_type_distribution": {
            row.table_type or "unknown": row.count 
            for row in table_type_stats
        },
        "extraction_methods": {
            row.method or "unknown": {
                "count": row.count,
                "avg_confidence": round(float(row.avg_confidence or 0), 2),
                "avg_quality": round(float(row.avg_quality or 0), 2)
            }
            for row in extraction_method_stats
        },
        "data_quality_distribution": {
            row.quality_level: row.count 
            for row in quality_stats
        }
    }

@app.get("/debug/document/{document_id}")
async def debug_document_raw(document_id: int, db: Session = Depends(get_db)):
    """Debug endpoint to see raw document data."""
    from src.adapters.database.models import DocumentRecord
    
    db_document = db.query(DocumentRecord).filter(DocumentRecord.id == document_id).first()
    if not db_document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {
        "id": db_document.id,
        "filename": db_document.filename,
        "table_count": db_document.table_count,
        "tables_data_type": str(type(db_document.tables_data)),
        "tables_data_length": len(db_document.tables_data) if db_document.tables_data else 0,
        "tables_data": db_document.tables_data[:2] if db_document.tables_data else None  # First 2 tables only
    }

@app.get("/health")
async def health_check():
    """Enhanced health check with table extraction status."""
    health = {
        "status": "healthy",
        "backend": "celery" if USE_CELERY else "background_tasks"
    }
    
    # Check table extraction capabilities
    try:
        import fitz
        health["pdf_table_extraction"] = "available"
    except ImportError:
        health["pdf_table_extraction"] = "unavailable"
        health["status"] = "degraded"
    
    try:
        import docx
        health["docx_table_extraction"] = "available"
    except ImportError:
        health["docx_table_extraction"] = "unavailable"
        health["status"] = "degraded"
    
    return health