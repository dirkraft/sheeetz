from .base import FileInfo


class GoogleDriveBackend:
    def __init__(self, credentials: dict):
        self._credentials = credentials

    async def list_files(self, folder_id: str) -> list[FileInfo]:
        raise NotImplementedError("Google Drive listing not yet implemented")

    async def download_file(self, file_id: str) -> bytes:
        raise NotImplementedError("Google Drive download not yet implemented")

    async def get_metadata(self, file_id: str) -> dict[str, str]:
        raise NotImplementedError("Google Drive metadata read not yet implemented")

    async def set_metadata(self, file_id: str, metadata: dict[str, str]) -> None:
        raise NotImplementedError("Google Drive metadata write not yet implemented")
