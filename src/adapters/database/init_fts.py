# src/infrastructure/database/init_fts.py
"""
Database initialization script for PostgreSQL Full-Text Search setup.
This script ensures proper FTS configuration and indexes.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

def setup_fts_extensions(db: Session):
    """Set up PostgreSQL extensions and configurations for FTS."""
    
    # Enable required extensions (if not already enabled)
    try:
        db.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent;"))
        db.commit()
        print("✓ Unaccent extension enabled")
    except Exception as e:
        print(f"Warning: Could not enable unaccent extension: {e}")
    
    # Create custom text search configuration (optional, for better language support)
    try:
        db.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_ts_config WHERE cfgname = 'english_unaccent'
                ) THEN
                    CREATE TEXT SEARCH CONFIGURATION english_unaccent (COPY = english);
                    ALTER TEXT SEARCH CONFIGURATION english_unaccent
                        ALTER MAPPING FOR hword, hword_part, word
                        WITH unaccent, english_stem;
                END IF;
            END
            $$;
        """))
        db.commit()
        print("✓ Custom FTS configuration created")
    except Exception as e:
        print(f"Warning: Could not create custom FTS configuration: {e}")

def create_fts_indexes(db: Session):
    """Create GIN indexes for full-text search performance."""
    
    # Create GIN index on search_vector if it doesn't exist
    try:
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_documents_search_vector_gin 
            ON documents USING gin(search_vector);
        """))
        db.commit()
        print("✓ GIN index on search_vector created")
    except Exception as e:
        print(f"Warning: Could not create GIN index: {e}")
    
    # Create additional indexes for common queries
    try:
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_documents_processing_method 
            ON documents(processing_method);
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_documents_has_ocr 
            ON documents(has_ocr_content);
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_documents_created_at_desc 
            ON documents(created_at DESC);
        """))
        db.commit()
        print("✓ Additional performance indexes created")
    except Exception as e:
        print(f"Warning: Could not create additional indexes: {e}")

def create_fts_trigger(db: Session):
    """Create trigger to automatically update search_vector on INSERT/UPDATE."""
    
    try:
        # Create trigger function
        db.execute(text("""
            CREATE OR REPLACE FUNCTION update_search_vector() 
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.search_vector := to_tsvector('english', 
                    coalesce(NEW.filename, '') || ' ' || 
                    coalesce(NEW.full_text, '') || ' ' || 
                    coalesce(NEW.author, '')
                );
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))
        
        # Create trigger
        db.execute(text("""
            DROP TRIGGER IF EXISTS update_documents_search_vector ON documents;
            CREATE TRIGGER update_documents_search_vector
                BEFORE INSERT OR UPDATE ON documents
                FOR EACH ROW EXECUTE FUNCTION update_search_vector();
        """))
        
        db.commit()
        print("✓ Automatic search_vector update trigger created")
    except Exception as e:
        print(f"Warning: Could not create FTS trigger: {e}")

def initialize_fts(db: Session):
    """Initialize all FTS components."""
    print("Initializing PostgreSQL Full-Text Search...")
    
    setup_fts_extensions(db)
    create_fts_indexes(db)
    create_fts_trigger(db)
    
    print("✓ PostgreSQL FTS initialization complete")

def update_existing_search_vectors(db: Session):
    """Update search vectors for existing documents."""
    try:
        result = db.execute(text("""
            UPDATE documents 
            SET search_vector = to_tsvector('english', 
                coalesce(filename, '') || ' ' || 
                coalesce(full_text, '') || ' ' || 
                coalesce(author, '')
            )
            WHERE search_vector IS NULL;
        """))
        db.commit()
        print(f"✓ Updated search vectors for {result.rowcount} existing documents")
    except Exception as e:
        print(f"Warning: Could not update existing search vectors: {e}")