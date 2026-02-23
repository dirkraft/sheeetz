from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class FileInfo:
    file_id: str
    name: str
    mime_type: str
    folder_path: str = ""
    size_bytes: int = 0
    metadata: dict[str, str] = field(default_factory=dict)


class StorageBackend(Protocol):
    async def list_files(self, folder_id: str) -> list[FileInfo]: ...

    async def download_file(self, file_id: str) -> bytes: ...

    async def get_metadata(self, file_id: str) -> dict[str, str]: ...

    async def set_metadata(self, file_id: str, metadata: dict[str, str]) -> None: ...
