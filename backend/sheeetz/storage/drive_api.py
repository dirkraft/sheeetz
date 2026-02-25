import json

import httpx

from ..config import settings

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_API = "https://www.googleapis.com/drive/v3"


class DriveTokenError(Exception):
    pass


async def get_valid_token(user) -> tuple[str, str]:
    """Refresh and return (access_token, updated_token_json)."""
    if not user.drive_token_json:
        raise DriveTokenError("No Drive tokens stored")

    token_data = json.loads(user.drive_token_json)
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        raise DriveTokenError("No refresh token available")

    async with httpx.AsyncClient() as client:
        resp = await client.post(GOOGLE_TOKEN_URL, data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
        if resp.status_code != 200:
            raise DriveTokenError(f"Token refresh failed: {resp.text}")
        new_tokens = resp.json()

    token_data["access_token"] = new_tokens["access_token"]
    if "refresh_token" in new_tokens:
        token_data["refresh_token"] = new_tokens["refresh_token"]

    return new_tokens["access_token"], json.dumps(token_data)


async def list_folders(access_token: str, parent_id: str = "root") -> list[dict]:
    """List subfolders of a given parent folder."""
    query = (
        f"'{parent_id}' in parents "
        "and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    params = {
        "q": query,
        "fields": "files(id,name,mimeType),nextPageToken",
        "orderBy": "name",
        "pageSize": 100,
    }
    headers = {"Authorization": f"Bearer {access_token}"}

    folders = []
    async with httpx.AsyncClient() as client:
        while True:
            resp = await client.get(f"{DRIVE_API}/files", params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            folders.extend(data.get("files", []))
            next_page = data.get("nextPageToken")
            if not next_page:
                break
            params["pageToken"] = next_page

    return folders


async def get_folder_info(access_token: str, folder_id: str) -> dict:
    """Get name and parents of a single folder."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{DRIVE_API}/files/{folder_id}",
            params={"fields": "id,name,parents"},
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


async def build_folder_path(access_token: str, folder_id: str) -> str:
    """Walk parents to build a path like /My Drive/Music/Jazz."""
    parts = []
    current_id = folder_id
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        for _ in range(20):
            resp = await client.get(
                f"{DRIVE_API}/files/{current_id}",
                params={"fields": "id,name,parents"},
                headers=headers,
            )
            resp.raise_for_status()
            info = resp.json()
            parts.append(info["name"])
            parents = info.get("parents", [])
            if not parents:
                break
            current_id = parents[0]

    parts.reverse()
    return "/" + "/".join(parts)


async def download_file(access_token: str, file_id: str) -> bytes:
    """Download file content from Google Drive."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{DRIVE_API}/files/{file_id}",
            params={"alt": "media"},
            headers=headers,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.content


async def list_pdf_files_recursive(access_token: str, folder_id: str) -> list[dict]:
    """Recursively list all PDF files under a folder.

    Returns list of {"id": str, "name": str, "folder_path": str}.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    results: list[dict] = []

    async def _collect(fid: str, path_prefix: str):
        # List PDFs in this folder
        query = (
            f"'{fid}' in parents "
            "and mimeType = 'application/pdf' "
            "and trashed = false"
        )
        params: dict = {
            "q": query,
            "fields": "files(id,name),nextPageToken",
            "pageSize": 1000,
        }
        async with httpx.AsyncClient() as client:
            while True:
                resp = await client.get(
                    f"{DRIVE_API}/files", params=params, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
                for f in data.get("files", []):
                    results.append({
                        "id": f["id"],
                        "name": f["name"],
                        "folder_path": path_prefix,
                    })
                next_page = data.get("nextPageToken")
                if not next_page:
                    break
                params["pageToken"] = next_page

        # Recurse into subfolders
        subfolders = await list_folders(access_token, fid)
        for sf in subfolders:
            sub_path = f"{path_prefix}/{sf['name']}" if path_prefix else sf["name"]
            await _collect(sf["id"], sub_path)

    await _collect(folder_id, "")
    return results
