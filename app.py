import sys
import datetime
from config import DB_DETAILS
import read
import write


def main():
    if len(sys.argv) < 2:
        print("Usage: python app.py [env]")
        sys.exit(1)

    env = sys.argv[1]
    db_details = DB_DETAILS[env]

    # Initialize connection handles
    target_conn = write.get_postgres_connection(db_details['TARGET_DB'])

    # Ensure both staging and production table frameworks are live in Docker
    write.ensure_database_schema_exists(target_conn)

    # Scan all local folders for raw files
    root_folder = "data"
    print(f"Initial directory scan to extract raw files inside: '{root_folder}'...")
    target_file_list = read.scan_all_transcript_files(root_folder)

    if not target_file_list:
        print("No data files found. Exiting.")
        target_conn.close()
        return

    # Extract all JSON file payloads exactly as they are without processing them in Python
    raw_payloads_master_list = []
    for current_file_path in target_file_list:
        payload = read.extract_clinic_transcripts_json(current_file_path)
        if payload:
            raw_payloads_master_list.append(payload)

    if raw_payloads_master_list:
        start_time = datetime.datetime.now()

        # dump the files directly into staging area
        write.load_raw_json_batch(target_conn, raw_payloads_master_list)

        # call the writer to execute SQL engine
        print("Executing PostgreSQL transformation query...")
        write.execute_transform_and_warehouse_load(target_conn)

        # Log performance metric output
        end_time = datetime.datetime.now()
        duration = (end_time - start_time).total_seconds()
        print(f"[{end_time.strftime('%Y-%m-%d %H:%M:%S')}] SUCCESS: Migrated {len(raw_payloads_master_list)} "
              f"records via SQL Query Engine in {duration:.4f} seconds.")

    target_conn.close()


if __name__ == '__main__':
    main()