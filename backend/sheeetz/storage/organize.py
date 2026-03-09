"""Path template parsing and resolution for the organize-files feature.

Template syntax:
  ($composer or $artist)/($title or $filename).$ext

Rules:
  - Segments are separated by /
  - ($a or $b or $c) — fallback group: use first non-empty value
  - $varname — single variable reference (must be non-empty)
  - Anything else is a literal
  - $filename — special: stem of the original filename (no extension)
  - $ext — special: file extension without dot (e.g. "pdf")
"""

import re
import shutil
from pathlib import Path


# Matches: (fallback group) | $varname | literal text
_TOKEN_RE = re.compile(r'\(([^)]+)\)|\$(\w+)|([^$(\n]+)')


def _parse_segment(seg: str) -> list:
    """Parse one path segment into a list of parts.

    Each part is either:
    - str: a literal string
    - list[str]: fallback group — use first non-empty key value
    """
    parts: list = []
    for m in _TOKEN_RE.finditer(seg):
        if m.group(1):  # ($a or $b or $c)
            keys = [k.strip().lstrip('$') for k in m.group(1).split(' or ')]
            parts.append(keys)
        elif m.group(2):  # $var
            parts.append([m.group(2)])
        else:  # literal
            parts.append(m.group(3))
    return parts


def parse_template(template: str) -> list[list]:
    """Parse a path template into segments (split by '/')."""
    return [_parse_segment(seg) for seg in template.split('/')]


def _sanitize(s: str) -> str:
    """Remove characters invalid in file/folder names."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', s).strip()


def resolve_template(
    template: str, vars: dict[str, str]
) -> tuple[str | None, list[str]]:
    """Resolve a path template given variable bindings.

    Returns (relative_path, warnings).
    Returns (None, [warning]) if any segment cannot be resolved.
    """
    segments = parse_template(template)
    resolved = []
    for seg_parts in segments:
        seg_value = ''
        for part in seg_parts:
            if isinstance(part, str):
                seg_value += part
            else:
                found = ''
                for key in part:
                    v = vars.get(key, '')
                    if v:
                        found = v
                        break
                if not found:
                    if len(part) == 1:
                        label = f'${part[0]}'
                    else:
                        label = '(' + ' or '.join(f'${k}' for k in part) + ')'
                    return None, [f'No value for {label}']
                seg_value += found
        resolved.append(_sanitize(seg_value))
    return '/'.join(resolved), []


def build_vars(sheet) -> dict[str, str]:
    """Build the variable map for a sheet (metadata + builtins)."""
    file_id: str = sheet.backend_file_id
    if '/' in file_id or '\\' in file_id:
        p = Path(file_id)
        filename_stem = p.stem
        ext = p.suffix.lstrip('.')
    else:
        # Drive file ID — derive from sheet.filename
        p = Path(sheet.filename)
        filename_stem = p.stem
        ext = p.suffix.lstrip('.')

    vars: dict[str, str] = {
        'filename': filename_stem,
        'ext': ext or 'pdf',
    }
    for entry in sheet.metadata_entries:
        vars[entry.key] = entry.value
    return vars


async def move_local_file(
    sheet,
    new_rel_path: str,
    db,
) -> None:
    """Move a local file to new_rel_path relative to its library folder root."""
    folder_root = Path(sheet.library_folder.backend_folder_id)
    old_path = Path(sheet.backend_file_id)
    new_abs = folder_root / new_rel_path

    if old_path.resolve() != new_abs.resolve():
        new_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_path), str(new_abs))

    # Compute new folder_path (relative to library folder root)
    new_dir = new_abs.parent
    try:
        rel_dir = new_dir.relative_to(folder_root)
        folder_path = str(rel_dir) if str(rel_dir) != '.' else ''
    except ValueError:
        folder_path = ''

    sheet.backend_file_id = str(new_abs)
    sheet.filename = new_abs.name
    sheet.folder_path = folder_path
    await db.commit()


async def move_drive_file(
    sheet,
    new_rel_path: str,
    access_token: str,
    db,
) -> None:
    """Move a Drive file according to new_rel_path.

    new_rel_path is like "Ludwig van Beethoven/Sonata No. 14.pdf".
    Segments except the last are folder names to create/find under the library root.
    The last segment is the new filename.
    """
    from ..storage.drive_api import get_or_create_drive_folder, move_and_rename_drive_file

    parts = new_rel_path.split('/')
    new_filename = parts[-1]
    folder_names = parts[:-1]

    # Walk/create folder hierarchy under library root
    parent_id = sheet.library_folder.backend_folder_id
    for name in folder_names:
        parent_id = await get_or_create_drive_folder(access_token, parent_id, name)

    # Current parent: we need to know it to remove old parent
    # For Drive, we track the file's current parent via folder_path reconstruction.
    # Since we don't store the parent folder ID directly, pass the library root as old parent.
    # Drive API handles multiple parents gracefully.
    old_parent_id = sheet.library_folder.backend_folder_id

    await move_and_rename_drive_file(
        access_token,
        file_id=sheet.backend_file_id,
        new_name=new_filename,
        new_parent_id=parent_id,
        old_parent_id=old_parent_id,
    )

    # Update DB
    folder_path = '/'.join(folder_names)
    sheet.filename = new_filename
    sheet.folder_path = folder_path
    await db.commit()
