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
    """Create trigger to automatically update search_vector on INSERT/UPDATE, including table data."""
    
    try:
        # Create helper function to extract text from tables_data JSON
        db.execute(text("""
            CREATE OR REPLACE FUNCTION extract_table_text(tables_data JSON) 
            RETURNS TEXT AS $$
            DECLARE
                table_text TEXT := '';
                table_record JSON;
                cell_value TEXT;
                row_elem JSON;
                data_elem JSON;
            BEGIN
                -- Return empty if no tables
                IF tables_data IS NULL THEN
                    RETURN '';
                END IF;
                
                -- Loop through each table in the array
                FOR table_record IN SELECT * FROM json_array_elements(tables_data)
                LOOP
                    -- Extract table title
                    table_text := table_text || ' ' || coalesce(table_record->>'title', '');
                    
                    -- Extract headers
                    IF table_record->'headers' IS NOT NULL THEN
                        SELECT string_agg(value::text, ' ') INTO cell_value
                        FROM json_array_elements_text(table_record->'headers');
                        table_text := table_text || ' ' || coalesce(cell_value, '');
                    END IF;
                    
                    -- Extract row data (limit to prevent performance issues)
                    IF table_record->'rows' IS NOT NULL THEN
                        -- For rows that are arrays of values
                        SELECT string_agg(elem::text, ' ') INTO cell_value
                        FROM (
                            SELECT json_array_elements_text(row_elem) as elem
                            FROM json_array_elements(table_record->'rows') as row_elem
                            LIMIT 1000  -- Limit rows to index for performance
                        ) subq;
                        table_text := table_text || ' ' || coalesce(cell_value, '');
                    END IF;
                    
                    -- Extract data field (for key-value format tables)
                    IF table_record->'data' IS NOT NULL THEN
                        -- Simply convert the data array to text for indexing
                        cell_value := table_record->'data'::text;
                        table_text := table_text || ' ' || coalesce(cell_value, '');
                    END IF;
                END LOOP;
                
                RETURN table_text;
            END;
            $$ LANGUAGE plpgsql IMMUTABLE;
        """))
        
        # Create trigger function that includes table data
        db.execute(text("""
            CREATE OR REPLACE FUNCTION update_search_vector() 
            RETURNS TRIGGER AS $$
            DECLARE
                table_content TEXT := '';
            BEGIN
                -- Extract table text if tables_data exists
                IF NEW.tables_data IS NOT NULL THEN
                    table_content := extract_table_text(NEW.tables_data);
                END IF;
                
                -- Create search vector from all searchable fields including tables
                -- Limit total text to 900KB to stay under tsvector's 1MB limit
                NEW.search_vector := to_tsvector('english', 
                    substring(
                        coalesce(NEW.filename, '') || ' ' || 
                        coalesce(NEW.full_text, '') || ' ' || 
                        coalesce(NEW.author, '') || ' ' ||
                        coalesce(table_content, '')
                        from 1 for 900000
                    )
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
        print("✓ Automatic search_vector update trigger created (with table data indexing)")
    except Exception as e:
        print(f"Warning: Could not create FTS trigger: {e}")
        import traceback
        traceback.print_exc()

def initialize_fts(db: Session):
    """Initialize all FTS components."""
    print("Initializing PostgreSQL Full-Text Search...")
    
    setup_fts_extensions(db)
    create_fts_indexes(db)
    create_fts_trigger(db)
    
    print("✓ PostgreSQL FTS initialization complete")

def update_existing_search_vectors(db: Session):
    """Update search vectors for existing documents, including table data."""
    try:
        # First, ensure the helper function exists
        db.execute(text("""
            CREATE OR REPLACE FUNCTION extract_table_text(tables_data JSON) 
            RETURNS TEXT AS $$
            DECLARE
                table_text TEXT := '';
                table_record JSON;
                cell_value TEXT;
            BEGIN
                IF tables_data IS NULL THEN
                    RETURN '';
                END IF;
                
                FOR table_record IN SELECT * FROM json_array_elements(tables_data)
                LOOP
                    table_text := table_text || ' ' || coalesce(table_record->>'title', '');
                    
                    IF table_record->'headers' IS NOT NULL THEN
                        SELECT string_agg(value::text, ' ') INTO cell_value
                        FROM json_array_elements_text(table_record->'headers');
                        table_text := table_text || ' ' || coalesce(cell_value, '');
                    END IF;
                    
                    IF table_record->'rows' IS NOT NULL THEN
                        SELECT string_agg(elem::text, ' ') INTO cell_value
                        FROM (
                            SELECT json_array_elements_text(row_elem) as elem
                            FROM json_array_elements(table_record->'rows') as row_elem
                            LIMIT 1000
                        ) subq;
                        table_text := table_text || ' ' || coalesce(cell_value, '');
                    END IF;
                    
                    IF table_record->'data' IS NOT NULL THEN
                        -- Simply convert the data array to text for indexing
                        cell_value := table_record->'data'::text;
                        table_text := table_text || ' ' || coalesce(cell_value, '');
                    END IF;
                END LOOP;
                
                RETURN table_text;
            END;
            $$ LANGUAGE plpgsql IMMUTABLE;
        """))
        
        # Update all documents to include table data in search_vector
        # Limit total text to 900KB to stay under tsvector's 1MB limit
        result = db.execute(text("""
            UPDATE documents 
            SET search_vector = to_tsvector('english', 
                substring(
                    coalesce(filename, '') || ' ' || 
                    coalesce(full_text, '') || ' ' || 
                    coalesce(author, '') || ' ' ||
                    coalesce(extract_table_text(tables_data), '')
                    from 1 for 900000
                )
            );
        """))
        db.commit()
        print(f"✓ Updated search vectors for {result.rowcount} existing documents (including table data)")
    except Exception as e:
        print(f"Warning: Could not update existing search vectors: {e}")
        import traceback
        traceback.print_exc()
