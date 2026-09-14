import sys
import json
import psycopg2


def get_postgres_connection(config):
    #Must use this syntax to ensure  proper connection to the target PostgreSQL Docker container.
    try:
        return psycopg2.connect(
            host=config['DB_HOST'],
            database=config['DB_NAME'],
            user=config['DB_USER'],
            password=config['DB_PASS']
        )
    except Exception as err:
        print(f"Error connecting to PostgreSQL: {err}")
        sys.exit(1)


def ensure_database_schema_exists(target_conn):
    """
    Creates the 'staging table' and the final analytics table inside PostgreSQL.
    Addition (9/12/2026): Uses TEXT type to avoid length constraint crashes.
    """
    # Uses psychopg2 to establish the cursor to communicate with PostgreSQL
                                                # inside Docker via the simulated 'cursor' terminal
    cursor = target_conn.cursor()
    try:
        # Development wipe: drop the old restricted structures so they rebuild fresh
        cursor.execute("DROP TABLE IF EXISTS clinic_call_analytics;")
        cursor.execute("DROP TABLE IF EXISTS staging_raw_calls;")

        # 1. Create a Staging table using high-performance JSONB
        cursor.execute("""
            CREATE TABLE staging_raw_calls (
                id SERIAL PRIMARY KEY,
                raw_payload JSONB,
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. Create the final analytics database table using flexible TEXT types
        cursor.execute("""
            CREATE TABLE clinic_call_analytics (
                call_job_id TEXT PRIMARY KEY,       
                account_id TEXT,                    
                total_duration_seconds NUMERIC(10, 2),
                ivr_summary TEXT,
                full_transcript_preview TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        #.commit() essentially saves the insert draft
        target_conn.commit()
        print("Database infrastructure verified: Staging and Production tables are ready.")
    except Exception as err:
        print(f"Failed to build database schema: {err}")
        #.rollback() serves as an undo function for the script so that corrupted files are not
                                                    # left in directories (in case of losing connection)
        target_conn.rollback()

    finally:
        cursor.close()


def load_raw_json_batch(target_conn, raw_payloads_list):
    """Bulk dumps completely untouched raw JSON strings into the staging tier."""
    if not raw_payloads_list:
        return

    cursor = target_conn.cursor()
    #the query is the SQL text
    query = "INSERT INTO staging_raw_calls (raw_payload) VALUES (%s);"

    # Convert Python dictionaries back into flat JSON strings for Postgres insertion
    values = [(json.dumps(payload),) for payload in raw_payloads_list]

    try:
        cursor.executemany(query, values)
        target_conn.commit()
        #created a standardized status print record
        print(f"Staging Phase: Dumped {len(values)} raw JSON blobs into staging table.")
    except Exception as err:
        print(f"Failed to load raw staging data: {err}")
        target_conn.rollback()
    finally:
        cursor.close()


def execute_transform_and_warehouse_load(target_conn):
    """
    The Core Transformation Engine!
    Executes a pure PostgreSQL query to parse the JSON fields, calculate metrics,
    and upsert the data into the production warehouse.
    """
    cursor = target_conn.cursor()

    # Advanced SQL: Traverses JSON layers using -> and ->> operators,
    # calculates duration, aggregates IVR matches via a subquery, and handles duplicate keys safely.
    sql_query = """
        INSERT INTO clinic_call_analytics (
            call_job_id, account_id, total_duration_seconds, ivr_summary, full_transcript_preview
        )
        -- 1. ->> means "pull the text value out of this JSON key"
        SELECT 
            raw_payload->>'jobName' AS call_job_id,
            raw_payload->>'accountId' AS account_id,
            -- 2. -> means "stay inside the JSON object". 
            -- -1 grabs the very last item in an array (the end of the call).
            -- 0 grabs the very first item (the start of the call).
            -- CAST(... AS NUMERIC) converts the text timestamps into math-ready numbers.
            
            -- Compute duration by extracting elements from the first (0) and last (-1) nested array positions
            COALESCE(
                ROUND(
                    CAST(raw_payload->'results'->'speaker_labels'->'segments'->-1->>'end_time' AS NUMERIC) - 
                    CAST(raw_payload->'results'->'speaker_labels'->'segments'->0->>'start_time' AS NUMERIC), 
                    2
                ), 
                0.0
            ) AS total_duration_seconds,
            
            --looks for the phrase "[Option" inside the transcript.
            CASE 
                WHEN raw_payload->'results'->'transcripts'->0->>'transcript' LIKE '%[Option%' THEN 'IVR ENGAGED'
                ELSE 'NONE'
            END AS ivr_summary,
            
            -- UPPER makes it all caps. TRIM deletes spaces. 
            -- SUBSTRING ensures it cuts off at 255 characters
            -- clean, strip, capitalize, and truncate strings using SQL rather than Python syntax
            UPPER(TRIM(SUBSTRING(raw_payload->'results'->'transcripts'->0->>'transcript' FROM 1 FOR 255))) AS full_transcript_preview

        FROM staging_raw_calls
        
        -- If a file with the same call_job_id is processed again, update it instead of crashing.
        ON CONFLICT (call_job_id) DO UPDATE SET 
            total_duration_seconds = EXCLUDED.total_duration_seconds,
            full_transcript_preview = EXCLUDED.full_transcript_preview;
    """

    try:
        cursor.execute(sql_query)
        # Clear out staging table after data has been successfully processed into production
        cursor.execute("TRUNCATE TABLE staging_raw_calls;")
        #save
        target_conn.commit()
    except Exception as err:
        print(f"PostgreSQL execution transformation failed: {err}")
        #undo in this case
        target_conn.rollback()

    finally:
        cursor.close()
