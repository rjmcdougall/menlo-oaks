"""
Google Photos client for uploading face detection thumbnails.
Uses OAuth2 refresh token to upload to a specific Google account's library.
"""

import base64
import logging
from typing import Optional

import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest

logger = logging.getLogger(__name__)

PHOTOS_UPLOAD_URL = "https://photoslibrary.googleapis.com/v1/uploads"
PHOTOS_CREATE_URL = "https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate"
PHOTOS_SCOPE = "https://www.googleapis.com/auth/photoslibrary.appendonly"
TOKEN_URI = "https://oauth2.googleapis.com/token"


class GooglePhotosClient:
    """Uploads thumbnails to a named Google Photos album using OAuth2."""

    def __init__(self, client_id: str, client_secret: str, refresh_token: str, album_id: Optional[str] = None, album_name: str = "facedetection"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.album_name = album_name
        self._creds: Optional[Credentials] = None
        self._album_id: Optional[str] = album_id

    def _get_access_token(self) -> str:
        """Get a valid access token, refreshing if necessary."""
        if self._creds is None:
            self._creds = Credentials(
                token=None,
                refresh_token=self.refresh_token,
                token_uri=TOKEN_URI,
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=[PHOTOS_SCOPE],
            )

        if not self._creds.valid:
            self._creds.refresh(GoogleAuthRequest())

        return self._creds.token

    def _get_album_id(self) -> Optional[str]:
        """Return the pre-configured album ID, if set."""
        return self._album_id

    def upload_image(self, image_data: bytes, filename: str, description: str = "") -> Optional[str]:
        """
        Upload image bytes to the facedetection Google Photos album.

        Returns:
            Google Photos media item URL, or None on failure
        """
        try:
            token = self._get_access_token()
            album_id = self._get_album_id()

            # Step 1: Upload raw bytes to get an upload token
            upload_response = requests.post(
                PHOTOS_UPLOAD_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/octet-stream",
                    "X-Goog-Upload-Content-Type": "image/jpeg",
                    "X-Goog-Upload-Protocol": "raw",
                    "X-Goog-Upload-File-Name": filename,
                },
                data=image_data,
                timeout=30,
            )
            upload_response.raise_for_status()
            upload_token = upload_response.text

            # Step 2: Create the media item in the album
            body = {
                "newMediaItems": [{
                    "description": description,
                    "simpleMediaItem": {
                        "fileName": filename,
                        "uploadToken": upload_token,
                    }
                }]
            }
            if album_id:
                body["albumId"] = album_id

            create_response = requests.post(
                PHOTOS_CREATE_URL,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
                timeout=30,
            )
            create_response.raise_for_status()
            result = create_response.json()

            item = result.get("newMediaItemResults", [{}])[0]
            status = item.get("status", {})
            if status.get("message") not in ("OK", "Success", None) and status.get("code", 0) not in (0, 200):
                logger.error(f"Photos create failed: {status}")
                return None

            url = item.get("mediaItem", {}).get("productUrl")
            logger.info(f"Uploaded {filename} to album '{self.album_name}': {url}")
            return url

        except Exception as e:
            logger.error(f"Failed to upload {filename} to Google Photos: {e}")
            return None

    def upload_base64_thumbnail(self, thumbnail_data_url: str, filename: str, description: str = "") -> Optional[str]:
        """Upload a base64 data URL thumbnail to the facedetection album."""
        try:
            if "," not in thumbnail_data_url:
                logger.error("Invalid data URL format")
                return None

            _, b64_data = thumbnail_data_url.split(",", 1)
            image_data = base64.b64decode(b64_data)
            return self.upload_image(image_data, filename, description)

        except Exception as e:
            logger.error(f"Failed to decode/upload thumbnail: {e}")
            return None
