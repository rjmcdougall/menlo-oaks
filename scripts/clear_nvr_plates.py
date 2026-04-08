#!/usr/bin/env python3
"""
Clear all license plate entries stored on the UniFi Protect NVR.

UniFi Protect maintains a local "seen plates" database that accumulates over
time. This script connects directly to the NVR and removes every entry.

Usage:
  # Login with credentials:
  python clear_nvr_plates.py --username admin --password secret

  # Or with a browser session token:
  python clear_nvr_plates.py --token <TOKEN> [--csrf <CSRF>]

  # Dry run (list plates without deleting):
  python clear_nvr_plates.py --username admin --password secret --dry-run

  # Discover mode (print raw license plate data structure):
  python clear_nvr_plates.py --username admin --password secret --discover

Options:
  --host       NVR IP or hostname (default: 10.0.9.70)
  --port       NVR HTTPS port (default: 443)
  --dry-run    List plates found but do not delete
  --discover   Dump raw plate data from bootstrap and exit
  --yes        Skip confirmation prompt
"""

import argparse
import json
import os
import sys

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_HOST = "10.0.9.70"
DEFAULT_PORT = 443


class NVRClient:
    def __init__(self, host: str, port: int):
        self.base = f"https://{host}:{port}"
        self.session = requests.Session()
        self.session.verify = False

    def login(self, username: str, password: str):
        resp = self.session.post(
            f"{self.base}/api/auth/login",
            json={"username": username, "password": password},
            timeout=15,
        )
        resp.raise_for_status()
        csrf = resp.headers.get("x-updated-csrf-token") or resp.headers.get("x-csrf-token")
        if csrf:
            self.session.headers["x-csrf-token"] = csrf
        print(f"✅ Logged in as {username}")

    def use_token(self, token: str, csrf: str = None):
        host = self.base.split("//")[1].split(":")[0]
        self.session.cookies.set("TOKEN", token, domain=host)
        if csrf:
            self.session.headers["x-csrf-token"] = csrf
        print("✅ Using session token")

    def get(self, path: str) -> dict:
        resp = self.session.get(f"{self.base}{path}", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def delete(self, path: str) -> requests.Response:
        resp = self.session.delete(f"{self.base}{path}", timeout=15)
        resp.raise_for_status()
        return resp

    def patch(self, path: str, payload: dict) -> requests.Response:
        resp = self.session.patch(
            f"{self.base}{path}",
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        return resp


def discover(client: NVRClient):
    """Print all license-plate-related keys from the bootstrap."""
    print("\n🔍 Fetching bootstrap…")
    bootstrap = client.get("/proxy/protect/api/bootstrap")

    def find_plate_keys(obj, path=""):
        """Recursively find any key mentioning 'plate' or 'lpr'."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                p = f"{path}.{k}" if path else k
                if any(kw in k.lower() for kw in ("plate", "lpr", "licenseplate")):
                    preview = json.dumps(v)[:200]
                    print(f"  {p}: {preview}")
                find_plate_keys(v, p)
        elif isinstance(obj, list) and obj:
            find_plate_keys(obj[0], f"{path}[0]")

    print("\n📋 License-plate related keys in bootstrap:")
    find_plate_keys(bootstrap)

    # Also probe known candidate endpoints
    candidates = [
        "/proxy/protect/api/license-plates",
        "/proxy/protect/api/nvr/license-plates",
        "/proxy/protect/api/smart-detections/license-plates",
    ]
    print("\n🔍 Probing candidate endpoints:")
    for url in candidates:
        try:
            data = client.get(url)
            print(f"  ✅ {url} → {json.dumps(data)[:300]}")
        except requests.HTTPError as e:
            print(f"  ✗  {url} → HTTP {e.response.status_code}")
        except Exception as e:
            print(f"  ✗  {url} → {e}")


def get_plates(client: NVRClient) -> list:
    """
    Fetch the list of license plates from the NVR.
    Tries the dedicated endpoint first, then falls back to the bootstrap.
    Returns a list of dicts with at minimum 'id' and a display name.
    """
    # Attempt 1: dedicated endpoint
    try:
        data = client.get("/proxy/protect/api/license-plates")
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "data" in data:
            return data["data"]
    except requests.HTTPError:
        pass

    # Attempt 2: look in the NVR bootstrap under known keys
    try:
        bootstrap = client.get("/proxy/protect/api/bootstrap")
        nvr = bootstrap.get("nvr", {})

        # UniFi Protect 2.x / 3.x stores plates under various keys
        for key in ("licensePlates", "license_plates", "lprPlates", "plateList"):
            if key in nvr:
                raw = nvr[key]
                return raw if isinstance(raw, list) else list(raw.values())

        # Some versions expose per-camera plate lists
        plates = []
        for cam in bootstrap.get("cameras", []):
            for key in ("licensePlates", "license_plates", "lprPlates"):
                if key in cam:
                    for p in cam[key]:
                        p.setdefault("_camera", cam.get("name", cam.get("id")))
                        plates.append(p)
        if plates:
            return plates
    except Exception as e:
        print(f"⚠️  Bootstrap lookup failed: {e}")

    return []


def delete_plate(client: NVRClient, plate: dict) -> bool:
    """Delete a single plate entry. Returns True on success."""
    plate_id = plate.get("id")
    if not plate_id:
        return False

    # Try DELETE on the dedicated endpoint
    try:
        client.delete(f"/proxy/protect/api/license-plates/{plate_id}")
        return True
    except requests.HTTPError:
        pass

    # Some firmware versions use a PATCH to clear individual plate fields
    try:
        client.patch(f"/proxy/protect/api/license-plates/{plate_id}", {"deleted": True})
        return True
    except Exception:
        pass

    return False


def clear_via_bootstrap_patch(client: NVRClient) -> bool:
    """
    Fallback: clear the plate list by PATCHing the NVR config with an empty list.
    """
    try:
        bootstrap = client.get("/proxy/protect/api/bootstrap")
        nvr = bootstrap.get("nvr", {})
        nvr_id = nvr.get("id")
        if not nvr_id:
            return False

        for key in ("licensePlates", "license_plates", "lprPlates", "plateList"):
            if key in nvr:
                client.patch(f"/proxy/protect/api/nvr", {key: []})
                print(f"✅ Cleared NVR.{key} via PATCH")
                return True
    except Exception as e:
        print(f"⚠️  Bootstrap PATCH failed: {e}")
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Clear all license plate entries from a UniFi Protect NVR"
    )
    parser.add_argument("--host", default=os.environ.get("NVR_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--username", default=os.environ.get("NVR_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("NVR_PASSWORD"))
    parser.add_argument("--token", default=os.environ.get("NVR_TOKEN"))
    parser.add_argument("--csrf", default=os.environ.get("NVR_CSRF"))
    parser.add_argument("--dry-run", action="store_true", help="List plates but do not delete")
    parser.add_argument("--discover", action="store_true", help="Dump plate data structure and exit")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    if not args.token and not (args.username and args.password):
        print("❌ Provide --username/--password or --token")
        sys.exit(1)

    client = NVRClient(args.host, args.port)

    if args.token:
        client.use_token(args.token, args.csrf)
    else:
        client.login(args.username, args.password)

    if args.discover:
        discover(client)
        return

    plates = get_plates(client)

    if not plates:
        print("ℹ️  No license plates found on NVR (or endpoint not supported on this firmware).")
        print("   Run with --discover to inspect the data structure.")
        return

    print(f"\n📋 Found {len(plates)} plate(s) on NVR:")
    for p in plates[:50]:
        name = (
            p.get("licensePlate")
            or p.get("plate_number")
            or p.get("name")
            or p.get("id", "?")
        )
        cam = p.get("_camera", "")
        print(f"  • {name}" + (f"  [{cam}]" if cam else ""))
    if len(plates) > 50:
        print(f"  … and {len(plates) - 50} more")

    if args.dry_run:
        print("\n⚡ Dry run — nothing deleted.")
        return

    if not args.yes:
        ans = input(f"\n⚠️  Delete ALL {len(plates)} plate(s)? [y/N] ").strip().lower()
        if ans != "y":
            print("Aborted.")
            return

    deleted = 0
    failed_ids = []
    for p in plates:
        if delete_plate(client, p):
            deleted += 1
        else:
            failed_ids.append(p.get("id", "?"))

    if failed_ids:
        print(f"\n⚠️  {len(failed_ids)} plate(s) could not be deleted individually.")
        print("   Attempting bulk clear via PATCH…")
        if clear_via_bootstrap_patch(client):
            deleted += len(failed_ids)
            failed_ids = []

    print(f"\n✅ Deleted {deleted} / {len(plates)} plate(s).")
    if failed_ids:
        print(f"❌ {len(failed_ids)} failed: {failed_ids[:10]}")


if __name__ == "__main__":
    main()
