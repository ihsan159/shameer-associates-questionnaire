"""
storage.py
Supabase Storage integration for Shameer Associates Questionnaire & Architect Workspace.
Supports signed upload URLs (bypassing Vercel 4.5MB payload limit), signed download URLs,
and direct server-side uploads, with safe offline local fallback.
"""
import os
import uuid
import logging
import requests
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
SUPABASE_SERVICE_ROLE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
STORAGE_BUCKET = os.environ.get('SUPABASE_STORAGE_BUCKET', 'client-uploads')


def is_storage_configured():
    """Check if Supabase Storage is configured with URL and service role key."""
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def build_storage_path(session_token, file_id, original_filename):
    """Generate canonical object storage path: sessions/<token>/<file_id>_<filename>."""
    safe_name = secure_filename(original_filename) or f"upload_{file_id[:8]}"
    return f"sessions/{session_token}/{file_id}_{safe_name}"


def create_signed_upload_url(storage_path, expires_in=900):
    """
    Request a signed upload URL from Supabase Storage REST API.
    The client can PUT the file directly to this URL, bypassing Vercel serverless payload limits.
    """
    if not is_storage_configured():
        logger.info("[STORAGE] Supabase Storage not configured. Returning local fallback.")
        return None

    api_url = f"{SUPABASE_URL}/storage/v1/object/upload/sign/{STORAGE_BUCKET}/{storage_path}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": "application/json"
    }
    payload = {"expiresIn": expires_in}

    try:
        resp = requests.post(api_url, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            rel_url = data.get('url', '')
            # Construct absolute upload URL
            full_upload_url = f"{SUPABASE_URL}/storage/v1{rel_url}"
            return full_upload_url
        else:
            logger.error(f"[STORAGE] Failed to create signed upload URL: {resp.status_code} - {resp.text}")
            return None
    except Exception as e:
        logger.error(f"[STORAGE] Error calling Supabase Storage API: {e}")
        return None


def upload_file_bytes(storage_path, file_bytes, content_type='application/octet-stream'):
    """Upload binary data directly to Supabase Storage via REST API."""
    if not is_storage_configured():
        return False

    api_url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{storage_path}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": content_type,
        "x-upsert": "true"
    }

    try:
        resp = requests.post(api_url, headers=headers, data=file_bytes, timeout=30)
        return resp.status_code in (200, 201)
    except Exception as e:
        logger.error(f"[STORAGE] Direct upload error: {e}")
        return False


def create_signed_download_url(storage_path, expires_in=3600):
    """
    Generate a temporary signed download URL for an architect to securely access an upload.
    Valid for 60 minutes by default.
    """
    if not is_storage_configured():
        return None

    api_url = f"{SUPABASE_URL}/storage/v1/object/sign/{STORAGE_BUCKET}/{storage_path}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": "application/json"
    }
    payload = {"expiresIn": expires_in}

    try:
        resp = requests.post(api_url, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            rel_url = data.get('signedURL', '')
            return f"{SUPABASE_URL}/storage/v1{rel_url}"
        else:
            logger.error(f"[STORAGE] Failed to generate signed download URL: {resp.status_code} - {resp.text}")
            return None
    except Exception as e:
        logger.error(f"[STORAGE] Error generating signed download URL: {e}")
        return None
