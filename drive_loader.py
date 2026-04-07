"""
Google Drive folder reader: lists and downloads daily gate files
from a shared Google Drive folder (no API key needed, folder must be
shared as 'Anyone with the link').
"""

import os
import re
import shutil
import tempfile
import requests
import streamlit as st


DRIVE_FOLDER_URL = "https://drive.google.com/drive/folders/{folder_id}"
DRIVE_DOWNLOAD_URL = "https://drive.google.com/uc?export=download&id={file_id}"

# Browser-like headers to avoid bot detection on cloud servers
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def list_drive_files(folder_id: str) -> list[dict]:
    """List files in a public Google Drive folder by parsing the folder page.

    Returns list of dicts: [{id, name}, ...]
    """
    url = DRIVE_FOLDER_URL.format(folder_id=folder_id)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        st.error(f"Cannot access Drive folder: {e}")
        return []

    # Extract file IDs (33-char alphanumeric strings)
    all_ids = set(re.findall(r'"([a-zA-Z0-9_-]{33})"', resp.text))
    # Remove the folder ID itself
    all_ids.discard(folder_id)

    # Extract filenames
    filenames = re.findall(r'((?:Titan Safety|[-])[^"]*\.xls[mx]?)', resp.text)
    # Clean HTML entities
    filenames = [f.replace("&amp;", "&") for f in filenames]
    filenames = sorted(set(filenames))

    # Try to match IDs to filenames by downloading headers
    files = []
    id_list = sorted(all_ids)

    for fid in id_list:
        try:
            r = requests.head(
                DRIVE_DOWNLOAD_URL.format(file_id=fid),
                headers=_HEADERS, allow_redirects=True, timeout=10,
            )
            disp = r.headers.get("content-disposition", "")
            ct = r.headers.get("content-type", "")

            if r.status_code != 200:
                continue
            if "spreadsheet" not in ct and "octet-stream" not in ct and "excel" not in ct:
                continue

            # Extract filename from content-disposition
            name_match = re.search(r'filename="([^"]+)"', disp)
            if name_match:
                name = name_match.group(1)
                if name.endswith((".xls", ".xlsm", ".xlsx")):
                    files.append({"id": fid, "name": name})
        except requests.exceptions.RequestException:
            continue

    return files


def download_drive_files(folder_id: str, local_dir: str = None, force: bool = False) -> str:
    """Download all gate files from a Drive folder to a local temp directory.

    Returns the path to the local directory containing the files.
    If force=True, re-downloads all files.
    """
    if local_dir is None:
        local_dir = os.path.join(tempfile.gettempdir(), f"tar_gate_{folder_id[:8]}")

    if force and os.path.isdir(local_dir):
        shutil.rmtree(local_dir)

    os.makedirs(local_dir, exist_ok=True)

    # Check what we already have locally
    existing = set(os.listdir(local_dir))

    files = list_drive_files(folder_id)
    if not files:
        # If HEAD-based listing failed, try a simpler approach:
        # download all 33-char IDs and see what sticks
        st.warning("Could not list files via headers. Trying bulk download...")
        files = _bulk_list_drive_files(folder_id)

    if not files:
        st.error("No files found in Drive folder.")
        return local_dir

    new_count = 0
    progress = st.progress(0, text="Downloading from Google Drive...")

    for i, f in enumerate(files):
        progress.progress((i + 1) / len(files), text=f"Downloading {f['name'][:40]}...")

        # Skip if already downloaded
        if f["name"] in existing:
            continue

        try:
            resp = requests.get(
                DRIVE_DOWNLOAD_URL.format(file_id=f["id"]),
                headers=_HEADERS, timeout=30,
            )
            if resp.status_code == 200 and len(resp.content) > 100:
                local_path = os.path.join(local_dir, f["name"])
                with open(local_path, "wb") as fh:
                    fh.write(resp.content)
                new_count += 1
        except requests.exceptions.RequestException:
            continue

    progress.empty()

    total = len([f for f in os.listdir(local_dir)
                 if f.endswith((".xls", ".xlsm", ".xlsx"))])
    st.caption(f"Drive sync: {total} files ({new_count} new)")

    return local_dir


def _bulk_list_drive_files(folder_id: str) -> list[dict]:
    """Fallback: extract IDs from folder page and probe each one."""
    url = DRIVE_FOLDER_URL.format(folder_id=folder_id)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=20)
    except requests.exceptions.RequestException:
        return []

    all_ids = set(re.findall(r'"([a-zA-Z0-9_-]{33})"', resp.text))
    all_ids.discard(folder_id)

    files = []
    for fid in sorted(all_ids):
        try:
            r = requests.get(
                DRIVE_DOWNLOAD_URL.format(file_id=fid),
                headers=_HEADERS, timeout=15, stream=True,
            )
            disp = r.headers.get("content-disposition", "")
            name_match = re.search(r'filename="([^"]+)"', disp)
            if name_match:
                name = name_match.group(1)
                if name.endswith((".xls", ".xlsm", ".xlsx")):
                    # Save content
                    content = r.content
                    if len(content) > 100:
                        files.append({"id": fid, "name": name, "_content": content})
            r.close()
        except requests.exceptions.RequestException:
            continue

    return files


def extract_folder_id(url_or_id: str) -> str:
    """Extract folder ID from a Google Drive URL or return as-is if already an ID."""
    match = re.search(r"folders/([a-zA-Z0-9_-]+)", url_or_id)
    if match:
        return match.group(1)
    # Might already be just the ID
    if re.match(r"^[a-zA-Z0-9_-]{20,}$", url_or_id.strip()):
        return url_or_id.strip()
    return url_or_id.strip()
