#!/usr/bin/env python3
"""
Batch uploader for historical UniFi Protect face detection events.

Queries all face detection events from the NVR, downloads their thumbnails,
and uploads them to the facedetection Google Photos album.

Optionally also inserts records into the BigQuery facedetection table.

Usage:
  python backfill_face_photos.py \\
      --username admin --password secret \\
      [--host 10.0.99.253] [--days 90] [--dry-run] [--no-bigquery]

  # Full NVR history
  python backfill_face_photos.py --username admin --password secret --all

Credentials are also accepted via environment variables:
  NVR_USERNAME, NVR_PASSWORD, NVR_HOST
  GOOGLE_PHOTOS_CLIENT_ID, GOOGLE_PHOTOS_CLIENT_SECRET,
  GOOGLE_PHOTOS_REFRESH_TOKEN, GOOGLE_PHOTOS_ALBUM_ID
"""

import argparse
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional

import requests

# Suppress SSL warnings for the NVR's self-signed cert
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest

try:
    from google.cloud import bigquery
    BQ_AVAILABLE = True
except ImportError:
    BQ_AVAILABLE = False

# ---------------------------------------------------------------------------
# Defaults (override via args or env vars)
# ---------------------------------------------------------------------------
DEFAULT_HOST = "10.0.9.70"
DEFAULT_PORT = 443
DEFAULT_CHUNK_DAYS = 1    # fetch events in 1-day chunks (~71 face events/day on this NVR)
EVENTS_PAGE_SIZE = 500    # max events per API request

GCP_PROJECT = "menlo-oaks"
BQ_DATASET = "license_plates"
BQ_TABLE = "facedetection"

PHOTOS_ALBUM_ID = "AD5iog5asNQDoLP1b_78uUdTUoWsmXzdRmEIjvdWPC0fN-oPqTvpacpdQHojRDofohFWeppe-SoK"
PHOTOS_SCOPE = "https://www.googleapis.com/auth/photoslibrary.appendonly"
PHOTOS_UPLOAD_URL = "https://photoslibrary.googleapis.com/v1/uploads"
PHOTOS_CREATE_URL = "https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate"
TOKEN_URI = "https://oauth2.googleapis.com/token"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# NVR client
# ---------------------------------------------------------------------------
class NVRClient:
    """Minimal UniFi Protect HTTP client for face event retrieval."""

    def __init__(self, host: str, port: int,
                 username: str = None, password: str = None,
                 token: str = None, csrf: str = None):
        self.base = f"https://{host}:{port}"
        self.session = requests.Session()
        self.session.verify = False
        if token:
            self._use_token(token, csrf)
        else:
            self._login(username, password)

    def _use_token(self, token: str, csrf: str = None):
        """Use a pre-obtained session token instead of logging in."""
        self.session.cookies.set("TOKEN", token, domain=self.base.split("//")[1].split(":")[0])
        if csrf:
            self.session.headers["x-csrf-token"] = csrf
        logger.info("Using pre-obtained session token")

    def _login(self, username: str, password: str):
        resp = self.session.post(
            f"{self.base}/api/auth/login",
            json={"username": username, "password": password},
            timeout=30,
        )
        if resp.status_code != 200:
            body = resp.json() if resp.content else {}
            raise RuntimeError(
                f"NVR login failed: HTTP {resp.status_code} "
                f"{body.get('code','')} — {body.get('message', resp.text[:100])}"
            )
        csrf = resp.headers.get("x-updated-csrf-token") or resp.headers.get("x-csrf-token")
        if csrf:
            self.session.headers["x-csrf-token"] = csrf
        logger.info("Authenticated to UniFi Protect NVR")

    def get_face_events(self, start_ms: int, end_ms: int) -> list:
        """
        Fetch smartDetectZone events with face detection in the given time range.
        Returns the raw list of event dicts from the API.
        """
        params = {
            "type": "smartDetectZone",
            "smartDetectTypes[]": "face",
            "allCameras": "true",
            "start": str(start_ms),
            "end": str(end_ms),
            "limit": str(EVENTS_PAGE_SIZE),
            "orderDirection": "ASC",
        }
        resp = self.session.get(
            f"{self.base}/proxy/protect/api/events",
            params=params,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    def get_thumbnail(self, event_id: str) -> Optional[bytes]:
        """Download the JPEG thumbnail for a face detection event."""
        resp = self.session.get(
            f"{self.base}/proxy/protect/api/events/{event_id}/thumbnail",
            timeout=30,
        )
        if resp.status_code == 200 and resp.content:
            return resp.content
        logger.debug(f"  No thumbnail for event {event_id}: HTTP {resp.status_code}")
        return None


# ---------------------------------------------------------------------------
# Google Photos uploader
# ---------------------------------------------------------------------------
class PhotosUploader:
    """Upload JPEG bytes to a Google Photos album."""

    def __init__(self, client_id: str, client_secret: str, refresh_token: str, album_id: str):
        self.album_id = album_id
        self._creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=TOKEN_URI,
            client_id=client_id,
            client_secret=client_secret,
            scopes=[PHOTOS_SCOPE],
        )

    def _token(self) -> str:
        if not self._creds.valid:
            self._creds.refresh(GoogleAuthRequest())
        return self._creds.token

    def upload(self, image_bytes: bytes, filename: str, description: str = "") -> Optional[str]:
        """Upload image bytes. Returns the Google Photos product URL or None."""
        for attempt in range(1, 4):
            try:
                return self._upload_once(image_bytes, filename, description)
            except requests.exceptions.Timeout:
                if attempt < 3:
                    logger.warning(f"  Photos API timeout (attempt {attempt}/3), retrying…")
                    time.sleep(5 * attempt)
                else:
                    logger.error(f"  Photos API timed out after 3 attempts: {filename}")
                    return None
            except Exception as e:
                logger.error(f"  Photos upload failed: {e}")
                return None

    def _upload_once(self, image_bytes: bytes, filename: str, description: str) -> Optional[str]:
        token = self._token()

        upload_resp = requests.post(
            PHOTOS_UPLOAD_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/octet-stream",
                "X-Goog-Upload-Content-Type": "image/jpeg",
                "X-Goog-Upload-Protocol": "raw",
                "X-Goog-Upload-File-Name": filename,
            },
            data=image_bytes,
            timeout=60,
        )
        upload_resp.raise_for_status()
        upload_token = upload_resp.text

        create_resp = requests.post(
            PHOTOS_CREATE_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "albumId": self.album_id,
                "newMediaItems": [{
                    "description": description,
                    "simpleMediaItem": {"fileName": filename, "uploadToken": upload_token},
                }],
            },
            timeout=60,
        )
        create_resp.raise_for_status()
        result = create_resp.json()
        item = result.get("newMediaItemResults", [{}])[0]
        status = item.get("status", {})
        if status.get("code", 0) not in (0, 200) and status.get("message") not in ("OK", "Success", None):
            logger.warning(f"  Photos create status: {status}")
            return None
        return item.get("mediaItem", {}).get("productUrl")


# ---------------------------------------------------------------------------
# BigQuery helper
# ---------------------------------------------------------------------------
def get_bq_client():
    if not BQ_AVAILABLE:
        return None
    try:
        return bigquery.Client(project=GCP_PROJECT)
    except Exception as e:
        logger.warning(f"BigQuery unavailable: {e}")
        return None


def already_in_bigquery(bq_client, event_ids: set) -> set:
    """Return the subset of event_ids that are already in the facedetection table."""
    if not bq_client or not event_ids:
        return set()
    id_list = ", ".join(f"'{eid}'" for eid in event_ids)
    query = f"""
        SELECT DISTINCT event_id
        FROM `{GCP_PROJECT}.{BQ_DATASET}.{BQ_TABLE}`
        WHERE event_id IN ({id_list})
    """
    try:
        rows = list(bq_client.query(query).result())
        return {row.event_id for row in rows}
    except Exception as e:
        logger.warning(f"BigQuery dedup check failed: {e}")
        return set()


def insert_bq_record(bq_client, event: dict, thumbnail_url: Optional[str]):
    """Insert a face detection record into BigQuery."""
    if not bq_client:
        return
    table_ref = bq_client.dataset(BQ_DATASET).table(BQ_TABLE)
    now = datetime.now(tz=timezone.utc).isoformat()
    start_ms = event.get("start", 0)
    detection_ts = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).isoformat()

    # Determine detection_type and person_name from event metadata
    # UniFi Protect puts face recognition info in metadata; exact field varies by firmware
    meta = event.get("metadata", {})
    person_name = (
        meta.get("personName")
        or meta.get("person_name")
        or (meta.get("recognizedFace") or {}).get("name")
        or (meta.get("faceAttributes") or {}).get("person")
        or None
    )
    detection_type = "face_known" if person_name else "face_unknown"

    row = {
        "record_id": str(uuid.uuid4()),
        "detection_timestamp": detection_ts,
        "event_id": event.get("id"),
        "person_name": person_name,
        "detection_type": detection_type,
        "device_id": event.get("camera", "").upper().replace(":", "") or None,
        "thumbnail_url": thumbnail_url,
        "created_at": now,
    }
    errors = bq_client.insert_rows_json(table_ref, [row])
    if errors:
        logger.warning(f"  BigQuery insert errors: {errors}")


# ---------------------------------------------------------------------------
# Event iteration
# ---------------------------------------------------------------------------
def iter_time_chunks(start_dt: datetime, end_dt: datetime, chunk_days: int) -> Iterator[tuple]:
    """Yield (start_ms, end_ms) pairs covering [start_dt, end_dt] in chunks."""
    chunk = timedelta(days=chunk_days)
    cursor = start_dt
    while cursor < end_dt:
        chunk_end = min(cursor + chunk, end_dt)
        yield int(cursor.timestamp() * 1000), int(chunk_end.timestamp() * 1000)
        cursor = chunk_end


# ---------------------------------------------------------------------------
# Event metadata helpers
# ---------------------------------------------------------------------------
def describe_event(event: dict) -> str:
    """Return a one-line human-readable description of a face event."""
    meta = event.get("metadata", {})
    person = (
        meta.get("personName")
        or meta.get("person_name")
        or (meta.get("recognizedFace") or {}).get("name")
        or None
    )
    ts = datetime.fromtimestamp(event.get("start", 0) / 1000, tz=timezone.utc)
    camera = event.get("camera", "unknown")[:12]
    label = f"face_known ({person})" if person else "face_unknown"
    return f"{ts.strftime('%Y-%m-%d %H:%M')}  camera={camera}  {label}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(description="Backfill face detection thumbnails to Google Photos")
    p.add_argument("--host", default=os.environ.get("NVR_HOST", DEFAULT_HOST))
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--username", default=os.environ.get("NVR_USERNAME"))
    p.add_argument("--password", default=os.environ.get("NVR_PASSWORD"))
    p.add_argument("--token", default=os.environ.get("NVR_TOKEN"),
                   help="Pre-obtained TOKEN cookie value (avoids login lockout)")
    p.add_argument("--csrf", default=os.environ.get("NVR_CSRF"),
                   help="X-Csrf-Token value paired with --token")
    p.add_argument("--days", type=int, default=None, help="How many days back to fetch (default: all history)")
    p.add_argument("--all", dest="all_history", action="store_true", help="Fetch full NVR history (overrides --days)")
    p.add_argument("--since", help="Start date YYYY-MM-DD (overrides --days)")
    p.add_argument("--dry-run", action="store_true", help="Fetch and describe events but don't upload")
    p.add_argument("--no-bigquery", action="store_true", help="Skip BigQuery inserts")
    p.add_argument("--skip-existing-bq", action="store_true",
                   help="Skip events whose event_id is already in BigQuery facedetection table")
    p.add_argument("--log-first-event", action="store_true",
                   help="Print the raw JSON of the first event (useful for debugging metadata fields)")
    p.add_argument("--photos-client-id", default=os.environ.get("GOOGLE_PHOTOS_CLIENT_ID"))
    p.add_argument("--photos-client-secret", default=os.environ.get("GOOGLE_PHOTOS_CLIENT_SECRET"))
    p.add_argument("--photos-refresh-token", default=os.environ.get("GOOGLE_PHOTOS_REFRESH_TOKEN"))
    p.add_argument("--photos-album-id", default=os.environ.get("GOOGLE_PHOTOS_ALBUM_ID", PHOTOS_ALBUM_ID))
    return p.parse_args()


def main():
    args = parse_args()

    # --- Determine time range ---
    end_dt = datetime.now(tz=timezone.utc)
    if args.since:
        start_dt = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    elif args.all_history:
        # UniFi Protect didn't exist before 2019; go back 10 years to be safe
        start_dt = datetime(2019, 1, 1, tzinfo=timezone.utc)
    elif args.days:
        start_dt = end_dt - timedelta(days=args.days)
    else:
        start_dt = datetime(2019, 1, 1, tzinfo=timezone.utc)

    logger.info(f"Time range: {start_dt.date()} → {end_dt.date()}")

    # --- Connect to NVR ---
    if not args.token and not (args.username and args.password):
        logger.error("Provide either --token (+ --csrf) or --username + --password")
        sys.exit(1)
    nvr = NVRClient(args.host, args.port,
                    username=args.username, password=args.password,
                    token=args.token, csrf=args.csrf)

    # --- Photos uploader ---
    photos = None
    if not args.dry_run:
        if not all([args.photos_client_id, args.photos_client_secret, args.photos_refresh_token]):
            logger.error(
                "Google Photos credentials required. Set --photos-client-id / --photos-client-secret / "
                "--photos-refresh-token or the corresponding env vars."
            )
            sys.exit(1)
        photos = PhotosUploader(
            client_id=args.photos_client_id,
            client_secret=args.photos_client_secret,
            refresh_token=args.photos_refresh_token,
            album_id=args.photos_album_id,
        )
        logger.info(f"Google Photos album: {args.photos_album_id}")

    # --- BigQuery client ---
    bq = None
    if not args.no_bigquery and BQ_AVAILABLE:
        bq = get_bq_client()
        if bq:
            logger.info("BigQuery enabled — will insert records")
        else:
            logger.info("BigQuery unavailable — skipping BQ inserts")
    else:
        logger.info("BigQuery inserts disabled")

    # --- Main loop ---
    total_events = 0
    total_uploaded = 0
    total_skipped = 0
    total_no_thumbnail = 0
    seen_ids: set = set()   # dedup within this run
    logged_first = False

    for chunk_start_ms, chunk_end_ms in iter_time_chunks(start_dt, end_dt, DEFAULT_CHUNK_DAYS):
        chunk_start_str = datetime.fromtimestamp(chunk_start_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        chunk_end_str = datetime.fromtimestamp(chunk_end_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        logger.info(f"Fetching events {chunk_start_str} → {chunk_end_str} …")

        try:
            events = nvr.get_face_events(chunk_start_ms, chunk_end_ms)
        except Exception as e:
            logger.error(f"  Failed to fetch events: {e}")
            continue

        if not events:
            logger.info("  No face events in this window")
            continue

        if len(events) >= EVENTS_PAGE_SIZE:
            logger.warning(f"  ⚠ Hit page limit ({EVENTS_PAGE_SIZE}) — some events in this window may be missing. Reduce --chunk-days or split the date range.")
        logger.info(f"  Found {len(events)} face detection events")

        # Log raw structure of first event to help debug metadata fields
        if args.log_first_event and not logged_first and events:
            logger.info("--- First event raw JSON ---")
            print(json.dumps(events[0], indent=2))
            logger.info("--- End first event ---")
            logged_first = True

        # Optional: check BigQuery for already-processed event IDs
        if args.skip_existing_bq and bq:
            chunk_event_ids = {e["id"] for e in events if e.get("id")}
            already_done = already_in_bigquery(bq, chunk_event_ids)
            if already_done:
                logger.info(f"  {len(already_done)} events already in BigQuery — skipping")
        else:
            already_done = set()

        for event in events:
            event_id = event.get("id", "")
            total_events += 1

            # Dedup
            if event_id in seen_ids or event_id in already_done:
                total_skipped += 1
                continue
            seen_ids.add(event_id)

            description = describe_event(event)

            if args.dry_run:
                print(f"  [DRY RUN] {description}")
                continue

            # Download thumbnail
            thumbnail_bytes = nvr.get_thumbnail(event_id)
            if not thumbnail_bytes:
                total_no_thumbnail += 1
                logger.debug(f"  Skipped (no thumbnail): {description}")
                continue

            # Upload to Google Photos
            ts = datetime.fromtimestamp(event.get("start", 0) / 1000, tz=timezone.utc)
            filename = f"face_{ts.strftime('%Y%m%d_%H%M%S')}_{event_id[:8]}.jpg"
            thumbnail_url = photos.upload(thumbnail_bytes, filename=filename, description=description)

            if thumbnail_url:
                logger.info(f"  ✓ {description}")
                total_uploaded += 1
            else:
                logger.warning(f"  ✗ Upload failed: {description}")

            # Optional BigQuery insert
            if bq:
                try:
                    insert_bq_record(bq, event, thumbnail_url)
                except Exception as e:
                    logger.warning(f"  BigQuery insert failed: {e}")

            # Brief pause to avoid hammering the NVR and Photos API
            time.sleep(0.1)

        # Pause between chunks
        time.sleep(0.5)

    # --- Summary ---
    print()
    print("=" * 50)
    print(f"  Total face events found : {total_events}")
    if args.dry_run:
        print("  (dry run — nothing uploaded)")
    else:
        print(f"  Uploaded to Photos      : {total_uploaded}")
        print(f"  No thumbnail available  : {total_no_thumbnail}")
        print(f"  Skipped (duplicate)     : {total_skipped}")
    print("=" * 50)


if __name__ == "__main__":
    main()
