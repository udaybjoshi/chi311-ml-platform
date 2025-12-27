# Databricks notebook source
# MAGIC %md
# MAGIC # 01 - API to Volume Ingestion
# MAGIC 
# MAGIC **Purpose**: Fetch data from Chicago 311 API and save as JSON files in Volume
# MAGIC 
# MAGIC **Pattern**: API → JSON File → Volume (Landing Zone)
# MAGIC 
# MAGIC **Schedule**: Daily (fetches previous day's data)
# MAGIC 
# MAGIC **Source**: https://data.cityofchicago.org/resource/v6vf-nfxy.json
# MAGIC 
# MAGIC **Note**: Initial load writes in chunks (50K records per file) to avoid file size limits

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

import requests
import json
from datetime import datetime, timedelta
from pyspark.sql import functions as F

# API Configuration
API_URL = "https://data.cityofchicago.org/resource/v6vf-nfxy.json"
CHUNK_SIZE = 50000  # Records per file (keeps files under 128MB limit)

# Volume paths
CATALOG = "workspace"
LANDING_PATH = f"/Volumes/{CATALOG}/raw/chi311_landing"
INITIAL_PATH = f"{LANDING_PATH}/initial"
INCREMENTAL_PATH = f"{LANDING_PATH}/incremental"

# Safety limits
MAX_CHUNKS = 20  # Maximum files for initial load (20 x 50K = 1M records)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Widget Parameters
# MAGIC 
# MAGIC Run modes:
# MAGIC - `initial`: Full historical load (last 2 years, written in chunks)
# MAGIC - `incremental`: Daily incremental (yesterday's data)

# COMMAND ----------

dbutils.widgets.dropdown("load_type", "incremental", ["initial", "incremental"], "Load Type")
dbutils.widgets.text("days_back", "1", "Days Back (for incremental)")
dbutils.widgets.text("years_back", "2", "Years Back (for initial)")

load_type = dbutils.widgets.get("load_type")
days_back = int(dbutils.widgets.get("days_back"))
years_back = int(dbutils.widgets.get("years_back"))

print(f"Load Type: {load_type}")
print(f"Days Back: {days_back}")
print(f"Years Back: {years_back}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Helper Functions

# COMMAND ----------

def fetch_from_api(where_clause: str = None, limit: int = CHUNK_SIZE, offset: int = 0) -> list:
    """Fetch records from Chicago 311 API with pagination support"""
    
    params = {
        "$limit": limit,
        "$offset": offset,
        "$order": "created_date DESC"
    }
    
    if where_clause:
        params["$where"] = where_clause
    
    response = requests.get(API_URL, params=params)
    response.raise_for_status()
    
    return response.json()


def save_to_volume(records: list, path: str, filename: str) -> str:
    """Save records as JSON file to Volume"""
    
    full_path = f"{path}/{filename}"
    
    # Convert to JSON string (no indent to reduce file size)
    json_content = json.dumps(records)
    
    # Write to volume using dbutils
    dbutils.fs.put(full_path, json_content, overwrite=True)
    
    return full_path


def get_file_count(path: str) -> int:
    """Get count of files in a directory"""
    try:
        return len(dbutils.fs.ls(path))
    except:
        return 0

# COMMAND ----------

# MAGIC %md
# MAGIC ## Initial Load (Historical) - Chunked
# MAGIC 
# MAGIC Fetches historical data and saves in chunks (50K records per file).
# MAGIC This avoids the 128MB file size limit in Databricks.

# COMMAND ----------

if load_type == "initial":
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * years_back)
    
    where_clause = f"created_date >= '{start_date.strftime('%Y-%m-%d')}'"
    
    print(f"Initial Load: {start_date.date()} to {end_date.date()}")
    print(f"Where clause: {where_clause}")
    print(f"Chunk size: {CHUNK_SIZE:,} records per file")
    print(f"Max chunks: {MAX_CHUNKS}")
    print("=" * 60)
    
    # Fetch and save in chunks
    offset = 0
    file_count = 0
    total_records = 0
    
    while True:
        print(f"\nFetching records {offset:,} to {offset + CHUNK_SIZE:,}...")
        records = fetch_from_api(where_clause=where_clause, limit=CHUNK_SIZE, offset=offset)
        
        if not records:
            print("No more records to fetch")
            break
        
        # Save this chunk
        filename = f"chi311_initial_{end_date.strftime('%Y%m%d')}_part{file_count:03d}.json"
        saved_path = save_to_volume(records, INITIAL_PATH, filename)
        
        records_in_chunk = len(records)
        total_records += records_in_chunk
        file_count += 1
        
        print(f"✅ Saved {records_in_chunk:,} records to: {filename}")
        
        # Check if we got fewer records than requested (means we're at the end)
        if records_in_chunk < CHUNK_SIZE:
            print("Reached end of data (partial chunk)")
            break
        
        offset += CHUNK_SIZE
        
        # Safety limit
        if file_count >= MAX_CHUNKS:
            print(f"\n⚠️ Reached safety limit ({MAX_CHUNKS} files)")
            break
    
    print(f"\n{'='*60}")
    print(f"✅ Initial load complete!")
    print(f"   Total records: {total_records:,}")
    print(f"   Files created: {file_count}")
    print(f"   Location: {INITIAL_PATH}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Incremental Load (Daily)
# MAGIC 
# MAGIC Fetches records from the last N days (default: yesterday).
# MAGIC Uses `last_modified_date` to catch both new and updated records.

# COMMAND ----------

if load_type == "incremental":
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    # Use last_modified_date for true incremental (catches updates too)
    where_clause = f"last_modified_date >= '{start_date.strftime('%Y-%m-%dT00:00:00')}'"
    
    print(f"Incremental Load: {start_date.date()} to {end_date.date()}")
    print(f"Where clause: {where_clause}")
    print("=" * 60)
    
    # Fetch records (single request for incremental)
    records = fetch_from_api(where_clause=where_clause)
    print(f"Records fetched: {len(records):,}")
    
    if records:
        # Save to incremental directory with timestamp
        filename = f"chi311_incremental_{end_date.strftime('%Y%m%d_%H%M%S')}.json"
        saved_path = save_to_volume(records, INCREMENTAL_PATH, filename)
        print(f"✅ Saved to: {saved_path}")
    else:
        print("ℹ️ No new records to save")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify Files in Volume

# COMMAND ----------

print("Files in landing volume:")
print("=" * 60)

# List initial files
print("\n📂 Initial directory:")
try:
    files = dbutils.fs.ls(INITIAL_PATH)
    total_size = 0
    for f in sorted(files, key=lambda x: x.name):
        print(f"   {f.name} ({f.size:,} bytes)")
        total_size += f.size
    print(f"\n   Total: {len(files)} files, {total_size:,} bytes ({total_size/1024/1024:.1f} MB)")
except Exception as e:
    print(f"   (empty or error: {e})")

# List incremental files
print("\n📂 Incremental directory:")
try:
    files = dbutils.fs.ls(INCREMENTAL_PATH)
    total_size = 0
    for f in sorted(files, key=lambda x: x.name)[-10:]:  # Show last 10
        print(f"   {f.name} ({f.size:,} bytes)")
        total_size += f.size
    if len(files) > 10:
        print(f"   ... and {len(files) - 10} more files")
    print(f"\n   Total: {len(files)} files")
except Exception as e:
    print(f"   (empty or error: {e})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Sample Data Preview

# COMMAND ----------

# Read one file to preview
if load_type == "initial":
    sample_path = INITIAL_PATH
else:
    sample_path = INCREMENTAL_PATH

try:
    files = dbutils.fs.ls(sample_path)
    if files:
        latest_file = sorted(files, key=lambda x: x.name)[-1]
        print(f"Previewing: {latest_file.path}")
        print("-" * 60)
        
        df = spark.read.json(latest_file.path)
        print(f"Records in file: {df.count():,}")
        print(f"Columns: {len(df.columns)}")
        print(f"\nSchema:")
        df.printSchema()
        print(f"\nSample data:")
        display(df.limit(5))
except Exception as e:
    print(f"No files to preview: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

# Print summary
print("=" * 60)
print("INGESTION SUMMARY")
print("=" * 60)
print(f"Load Type: {load_type}")
print(f"Timestamp: {datetime.now()}")

if load_type == "initial":
    print(f"Date Range: {years_back} years back")
    print(f"Chunk Size: {CHUNK_SIZE:,} records per file")
else:
    print(f"Days Back: {days_back}")

print(f"\nOutput Location: {INITIAL_PATH if load_type == 'initial' else INCREMENTAL_PATH}")
print("=" * 60)
print("\n✅ Next Step: Run 02_bronze_autoloader.py to ingest files into Bronze Delta table")

# COMMAND ----------

# Return success
dbutils.notebook.exit("SUCCESS")