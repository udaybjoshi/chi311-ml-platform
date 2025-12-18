"""
NYC 311 Open Data API Client

This module provides a client for fetching 311 service request data from
the NYC Open Data portal (Socrata API).

ML Portfolio Framework Alignment:
- Component 2: Unique Data Sourcing
- Implements continuous data collection via API
- Includes data quality validation on ingestion
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Generator
from dataclasses import dataclass
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class APIConfig:
    """Configuration for NYC Open Data API."""
    
    base_url: str = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
    app_token: Optional[str] = None  # Optional but recommended for higher rate limits
    timeout: int = 30
    max_retries: int = 3
    retry_backoff: float = 0.5
    page_size: int = 10000  # Socrata default limit is 50000
    
    @classmethod
    def from_env(cls) -> "APIConfig":
        """Create config from environment variables."""
        return cls(
            base_url=os.getenv("NYC_OPENDATA_URL", cls.base_url),
            app_token=os.getenv("NYC_OPENDATA_APP_TOKEN"),
        )


@dataclass
class DataQualityReport:
    """Report on data quality for a fetch operation."""
    
    total_records: int
    null_unique_key: int
    null_created_date: int
    null_borough: int
    invalid_coordinates: int
    duplicate_keys: int
    date_range: tuple
    
    @property
    def is_valid(self) -> bool:
        """Check if data passes basic quality thresholds."""
        if self.total_records == 0:
            return True  # Empty is valid (might be no new data)
        
        # Thresholds
        null_rate_threshold = 0.05  # 5% max null rate
        
        null_rate = (self.null_unique_key + self.null_created_date) / self.total_records
        dupe_rate = self.duplicate_keys / self.total_records
        
        return null_rate < null_rate_threshold and dupe_rate < null_rate_threshold
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "total_records": self.total_records,
            "null_unique_key": self.null_unique_key,
            "null_created_date": self.null_created_date,
            "null_borough": self.null_borough,
            "invalid_coordinates": self.invalid_coordinates,
            "duplicate_keys": self.duplicate_keys,
            "date_range_start": str(self.date_range[0]) if self.date_range[0] else None,
            "date_range_end": str(self.date_range[1]) if self.date_range[1] else None,
            "is_valid": self.is_valid
        }


class NYC311APIClient:
    """
    Client for NYC Open Data 311 Service Requests API.
    
    Features:
    - Automatic pagination
    - Retry logic with exponential backoff
    - Data quality validation
    - Incremental loading support
    
    Example:
        client = NYC311APIClient()
        
        # Fetch last 7 days
        records = client.fetch_recent(days=7)
        
        # Incremental fetch since last load
        new_records = client.fetch_since("2024-01-15T00:00:00")
        
        # Validate data quality
        report = client.validate_records(records)
    """
    
    # NYC bounding box for coordinate validation
    NYC_LAT_MIN, NYC_LAT_MAX = 40.4, 41.0
    NYC_LON_MIN, NYC_LON_MAX = -74.3, -73.7
    
    # Required fields for basic validation
    REQUIRED_FIELDS = ["unique_key", "created_date", "complaint_type"]
    
    def __init__(self, config: Optional[APIConfig] = None):
        """Initialize the API client."""
        self.config = config or APIConfig.from_env()
        self.session = self._create_session()
        
    def _create_session(self) -> requests.Session:
        """Create a requests session with retry logic."""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.retry_backoff,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set headers
        headers = {"Accept": "application/json"}
        if self.config.app_token:
            headers["X-App-Token"] = self.config.app_token
        session.headers.update(headers)
        
        return session
    
    def _build_query(
        self,
        where: Optional[str] = None,
        select: Optional[str] = None,
        order: str = "created_date DESC",
        limit: Optional[int] = None,
        offset: int = 0
    ) -> str:
        """Build SoQL query string."""
        params = {
            "$order": order,
            "$offset": offset,
            "$limit": limit or self.config.page_size,
        }
        
        if where:
            params["$where"] = where
        if select:
            params["$select"] = select
            
        return urlencode(params)
    
    def _fetch_page(
        self,
        where: Optional[str] = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Fetch a single page of results."""
        query = self._build_query(where=where, offset=offset)
        url = f"{self.config.base_url}?{query}"
        
        logger.debug(f"Fetching: {url}")
        
        response = self.session.get(url, timeout=self.config.timeout)
        response.raise_for_status()
        
        return response.json()
    
    def fetch_all(
        self,
        where: Optional[str] = None,
        max_records: Optional[int] = None,
        progress_callback: Optional[callable] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Fetch all records matching the query, handling pagination.
        
        Args:
            where: SoQL WHERE clause
            max_records: Maximum total records to fetch
            progress_callback: Called with (records_fetched, total_estimate)
            
        Yields:
            Individual record dictionaries
        """
        offset = 0
        total_fetched = 0
        
        while True:
            try:
                records = self._fetch_page(where=where, offset=offset)
            except requests.RequestException as e:
                logger.error(f"API request failed at offset {offset}: {e}")
                raise
            
            if not records:
                logger.info(f"Completed fetch: {total_fetched} total records")
                break
                
            for record in records:
                yield record
                total_fetched += 1
                
                if max_records and total_fetched >= max_records:
                    logger.info(f"Reached max_records limit: {max_records}")
                    return
            
            if progress_callback:
                progress_callback(total_fetched, None)
                
            offset += len(records)
            
            # Rate limiting - be nice to the API
            time.sleep(0.1)
            
            # If we got fewer records than page size, we're done
            if len(records) < self.config.page_size:
                logger.info(f"Completed fetch: {total_fetched} total records")
                break
    
    def fetch_recent(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Fetch records from the last N days.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of record dictionaries
        """
        since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
        where = f"created_date >= '{since_date}'"
        
        logger.info(f"Fetching records since {since_date}")
        
        records = list(self.fetch_all(where=where))
        logger.info(f"Fetched {len(records)} records from last {days} days")
        
        return records
    
    def fetch_since(self, timestamp: str) -> List[Dict[str, Any]]:
        """
        Fetch records created since a specific timestamp.
        NOTE: This only gets NEW records, not updates. For SCD2, use fetch_changes_since().
        
        Args:
            timestamp: ISO format timestamp (e.g., "2024-01-15T00:00:00")
            
        Returns:
            List of record dictionaries
        """
        where = f"created_date > '{timestamp}'"
        
        logger.info(f"Fetching records since {timestamp}")
        
        records = list(self.fetch_all(where=where))
        logger.info(f"Fetched {len(records)} new records")
        
        return records
    
    def fetch_changes_since(self, timestamp: str) -> List[Dict[str, Any]]:
        """
        Fetch records that were created OR updated since a specific timestamp.
        Use this for SCD Type 2 incremental loading to capture status changes.
        
        This fetches records where:
        - created_date > timestamp (new requests)
        - OR resolution_action_updated_date > timestamp (status/resolution updates)
        - OR closed_date > timestamp (recently closed)
        
        Args:
            timestamp: ISO format timestamp (e.g., "2024-01-15T00:00:00")
            
        Returns:
            List of record dictionaries (may include duplicates if record was both created and updated)
        """
        where = (
            f"created_date > '{timestamp}' "
            f"OR resolution_action_updated_date > '{timestamp}' "
            f"OR closed_date > '{timestamp}'"
        )
        
        logger.info(f"Fetching new and updated records since {timestamp}")
        
        records = list(self.fetch_all(where=where))
        
        # Deduplicate by unique_key (keep latest version based on resolution_action_updated_date)
        seen = {}
        for record in records:
            key = record.get("unique_key")
            if key:
                existing = seen.get(key)
                if existing is None:
                    seen[key] = record
                else:
                    # Keep the one with more recent update
                    new_updated = record.get("resolution_action_updated_date", "")
                    old_updated = existing.get("resolution_action_updated_date", "")
                    if new_updated > old_updated:
                        seen[key] = record
        
        deduped_records = list(seen.values())
        
        logger.info(f"Fetched {len(records)} records, {len(deduped_records)} unique after deduplication")
        
        return deduped_records
    
    def fetch_date_range(
        self,
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch records within a date range.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            List of record dictionaries
        """
        where = f"created_date >= '{start_date}' AND created_date < '{end_date}'"
        
        logger.info(f"Fetching records from {start_date} to {end_date}")
        
        records = list(self.fetch_all(where=where))
        logger.info(f"Fetched {len(records)} records")
        
        return records
    
    def validate_records(self, records: List[Dict[str, Any]]) -> DataQualityReport:
        """
        Validate a list of records for data quality.
        
        Args:
            records: List of record dictionaries
            
        Returns:
            DataQualityReport with validation results
        """
        if not records:
            return DataQualityReport(
                total_records=0,
                null_unique_key=0,
                null_created_date=0,
                null_borough=0,
                invalid_coordinates=0,
                duplicate_keys=0,
                date_range=(None, None)
            )
        
        null_unique_key = sum(1 for r in records if not r.get("unique_key"))
        null_created_date = sum(1 for r in records if not r.get("created_date"))
        null_borough = sum(1 for r in records if not r.get("borough"))
        
        # Check coordinates
        invalid_coords = 0
        for r in records:
            lat = r.get("latitude")
            lon = r.get("longitude")
            if lat and lon:
                try:
                    lat_f, lon_f = float(lat), float(lon)
                    if not (self.NYC_LAT_MIN <= lat_f <= self.NYC_LAT_MAX and
                            self.NYC_LON_MIN <= lon_f <= self.NYC_LON_MAX):
                        invalid_coords += 1
                except (ValueError, TypeError):
                    invalid_coords += 1
        
        # Check duplicates
        unique_keys = [r.get("unique_key") for r in records if r.get("unique_key")]
        duplicate_keys = len(unique_keys) - len(set(unique_keys))
        
        # Date range
        dates = [r.get("created_date") for r in records if r.get("created_date")]
        date_range = (min(dates), max(dates)) if dates else (None, None)
        
        report = DataQualityReport(
            total_records=len(records),
            null_unique_key=null_unique_key,
            null_created_date=null_created_date,
            null_borough=null_borough,
            invalid_coordinates=invalid_coords,
            duplicate_keys=duplicate_keys,
            date_range=date_range
        )
        
        # Log report
        logger.info(f"Data Quality Report: {report.to_dict()}")
        
        if not report.is_valid:
            logger.warning("Data quality validation FAILED")
        
        return report


class IncrementalLoader:
    """
    Manages incremental loading of 311 data.
    
    Tracks the last loaded timestamp to only fetch new/updated records.
    
    For SCD Type 2 pipelines, use scd2_mode=True to capture both new
    records AND updates to existing records (status changes, resolutions).
    
    Example:
        loader = IncrementalLoader(client, scd2_mode=True)
        
        # First run - loads last 7 days
        records = loader.load_incremental()
        
        # Subsequent runs - loads new AND updated records since last run
        new_records = loader.load_incremental()
    """
    
    def __init__(
        self,
        client: NYC311APIClient,
        state_file: str = "/tmp/nyc311_loader_state.json",
        scd2_mode: bool = True  # Default to SCD2 mode
    ):
        """
        Initialize the loader.
        
        Args:
            client: NYC311APIClient instance
            state_file: Path to store last loaded timestamp
            scd2_mode: If True, fetch both new and updated records (for SCD2)
                      If False, only fetch new records
        """
        self.client = client
        self.state_file = state_file
        self.scd2_mode = scd2_mode
        
    def _read_state(self) -> Optional[str]:
        """Read last loaded timestamp from state file."""
        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)
                return state.get("last_loaded_timestamp")
        except (FileNotFoundError, json.JSONDecodeError):
            return None
    
    def _write_state(self, timestamp: str):
        """Write last loaded timestamp to state file."""
        with open(self.state_file, "w") as f:
            json.dump({
                "last_loaded_timestamp": timestamp,
                "scd2_mode": self.scd2_mode
            }, f)
    
    def load_incremental(
        self,
        initial_lookback_days: int = 7
    ) -> tuple[List[Dict[str, Any]], DataQualityReport]:
        """
        Load records incrementally since last run.
        
        In SCD2 mode, this fetches both:
        - New records (created_date > last_timestamp)
        - Updated records (resolution_action_updated_date > last_timestamp)
        
        Args:
            initial_lookback_days: Days to look back on first run
            
        Returns:
            Tuple of (records, quality_report)
        """
        last_timestamp = self._read_state()
        
        if last_timestamp:
            if self.scd2_mode:
                logger.info(f"SCD2 incremental load (new + updates) since {last_timestamp}")
                records = self.client.fetch_changes_since(last_timestamp)
            else:
                logger.info(f"Simple incremental load (new only) since {last_timestamp}")
                records = self.client.fetch_since(last_timestamp)
        else:
            logger.info(f"Initial load: last {initial_lookback_days} days")
            records = self.client.fetch_recent(days=initial_lookback_days)
        
        # Validate
        report = self.client.validate_records(records)
        
        # Update state if successful
        if records and report.date_range[1]:
            self._write_state(report.date_range[1])
            logger.info(f"Updated state: last_loaded_timestamp = {report.date_range[1]}")
        
        return records, report


# Convenience functions for Databricks notebooks
def fetch_recent_records(days: int = 7) -> List[Dict[str, Any]]:
    """Convenience function for fetching recent records."""
    client = NYC311APIClient()
    return client.fetch_recent(days=days)


def fetch_incremental(scd2_mode: bool = True) -> tuple[List[Dict[str, Any]], DataQualityReport]:
    """
    Convenience function for incremental loading.
    
    Args:
        scd2_mode: If True (default), fetch both new and updated records.
        Set to False to only fetch new records.
    """
    client = NYC311APIClient()
    loader = IncrementalLoader(client, scd2_mode=scd2_mode)
    return loader.load_incremental()


if __name__ == "__main__":
    # Example usage
    client = NYC311APIClient()
    
    # Fetch recent records
    records = client.fetch_recent(days=1)
    print(f"Fetched {len(records)} records")
    
    # Validate
    report = client.validate_records(records)
    print(f"Validation passed: {report.is_valid}")
    print(f"Report: {report.to_dict()}")