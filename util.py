import datetime


def process_call_analytics(raw_json_data):
    """
    Transforms native AWS Transcribe JSON payloads into structured rows.
    Extracts job variables, calculates call duration, and captures IVR strings.
    """
    if not raw_json_data:
        return []

    analytics_records = []

    #Capture top-level metadata values
    job_id = raw_json_data.get("jobName", "UNKNOWN_CALL")
    account_id = raw_json_data.get("accountId", "UNKNOWN_ACCT")

    #Extract nested values
    results_content = raw_json_data.get("results", {})

    #get transcripts from the array
    #isinstance() checks if the raw payloads have errors in the JSON formatting
    transcripts_list = results_content.get("transcripts", [])
    full_transcript_text = ""
    if transcripts_list and isinstance(transcripts_list, list):
        full_transcript_text = transcripts_list[0].get("transcript", "")

    #calculate timestamps
    speaker_labels_dict = results_content.get("speaker_labels", {})
    segments_list = []
    if isinstance(speaker_labels_dict, dict):
        segments_list = speaker_labels_dict.get("segments", [])

    #Calculate call duration: end time of final segment minus start of first segment
    total_duration_seconds = 0.0
    if segments_list and isinstance(segments_list, list):
        try:
            start_time = float(segments_list[0].get("start_time", 0.0))
            end_time = float(segments_list[-1].get("end_time", 0.0))
            total_duration_seconds = round(end_time - start_time, 2)
        except (IndexError, ValueError, KeyError):
            total_duration_seconds = 0.0

    #Scan the entire transcript text to store any IVR option instances (store in variable ivr_options_pressed)
    ivr_options_pressed = []
    if full_transcript_text:
        # Check for standard IVR option formatting
        for i in range(1, 10):
            option_flag = f"[Option {i}]"
            if option_flag in full_transcript_text:
                ivr_options_pressed.append(option_flag)

    #Create standardized dictionary for PostgreSQL
    cleaned_record = {
        "call_job_id": job_id,
        "account_id": account_id,
        "total_duration_seconds": total_duration_seconds,
        "ivr_summary": ", ".join(ivr_options_pressed) if ivr_options_pressed else "NONE",
        "full_transcript_preview": full_transcript_text[:255].strip(),  # Prevent database column size overflow
        "processed_at": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    analytics_records.append(cleaned_record)
    return analytics_records


def log_performance_metrics(table_name, count, start_time, end_time):
    #Calculates pipeline performance durations.
    duration = (end_time - start_time).total_seconds()
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
          f"SUCCESS: Analyzed and Migrated {count} metrics matrices to '{table_name}' in {duration:.4f} seconds.")
