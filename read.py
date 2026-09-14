import json
import sys
import os
import glob

def scan_all_transcript_files(root_data_directory):
    """
    Recursive: scans all directories and subdirectories inside the root folder.
    Returns a list of file paths for ALL JSON target data.
    """
    #.join() automatically detects user's operating system to write correct paths
    # Wildcard symbol (**) takes care of the file parsing
    search_pattern = os.path.join(root_data_directory, "**", "*.json")
    all_json_files = glob.glob(search_pattern, recursive=True)
    print(f"Directory Scanner: Found {len(all_json_files)} file footprints across data targets.")
    return all_json_files

def extract_clinic_transcripts_json(file_path):
    """
    Collects a raw JSON payload representing a medical clinic call transcript.
    Streams text data into Python dictionary objects.
    """
    try:
        with open(file_path, mode='r', encoding='utf-8') as file:
            data = json.load(file)
        return data
    except FileNotFoundError:
        print(f"Error: The file at {file_path} was not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Warning: Failed to parse JSON framework structure at {file_path}. Skipping.")
        return None
