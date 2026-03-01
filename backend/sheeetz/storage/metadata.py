"""Core sheet music metadata: extraction from PDF and mapping to standard fields."""

import io

import pikepdf

CORE_FIELDS = [
    {"key": "title", "label": "Title"},
    {"key": "composer", "label": "Composer"},
    {"key": "tags", "label": "Tags"},
    {"key": "pages", "label": "Pages"},
]

# Editable core field keys (pages is auto-derived, not user-editable)
EDITABLE_CORE_KEYS = {"title", "composer", "tags"}

SHEEETZ_NS = "http://sheeetz.app/meta/1.0/"

# Maps raw PDF metadata keys (lowercase) → core field key.
# Sheeetz namespace is checked first (highest priority), then standard keys.
RAW_TO_CORE_MAP: dict[str, str] = {
    # Sheeetz namespace (highest priority — user edits)
    f"{{{SHEEETZ_NS}}}title": "title",
    f"{{{SHEEETZ_NS}}}composer": "composer",
    f"{{{SHEEETZ_NS}}}tags": "tags",
    # Standard PDF/XMP keys (fallback from original PDF)
    "title": "title",
    "dc:title": "title",
    "{http://purl.org/dc/elements/1.1/}title": "title",
    "author": "composer",
    "dc:creator": "composer",
    "{http://purl.org/dc/elements/1.1/}creator": "composer",
    "keywords": "tags",
    "pdf:keywords": "tags",
    "{http://ns.adobe.com/pdf/1.3/}keywords": "tags",
}


def extract_pdf_metadata(pdf_bytes: bytes) -> dict[str, str]:
    """Extract all metadata from a PDF as a flat dict of strings."""
    meta: dict[str, str] = {}
    try:
        with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
            if pdf.docinfo:
                for key, val in pdf.docinfo.items():
                    k = str(key).lstrip("/")
                    meta[k] = str(val)

            with pdf.open_metadata(set_pikepdf_as_editor=False) as xmp:
                for key, val in xmp.items():
                    if val and str(val).strip():
                        meta[key] = str(val)

            meta["pages"] = str(len(pdf.pages))
    except Exception as e:
        meta["_error"] = str(e)

    return meta


def map_raw_to_core(raw_meta: dict[str, str]) -> dict[str, str]:
    """Map raw PDF metadata to core sheet music fields. First match wins per core key.

    Also extracts arbitrary sheeetz-namespace keys not in RAW_TO_CORE_MAP as custom fields.
    """
    core: dict[str, str] = {}

    # Always include pages if present
    if "pages" in raw_meta:
        core["pages"] = raw_meta["pages"]

    # Map raw keys to core keys (case-insensitive matching)
    raw_lower = {k.lower(): v for k, v in raw_meta.items()}
    seen_core_keys: set[str] = set()

    for raw_key_lower, core_key in RAW_TO_CORE_MAP.items():
        if core_key in seen_core_keys:
            continue
        value = raw_lower.get(raw_key_lower, "").strip()
        if value:
            core[core_key] = value
            seen_core_keys.add(core_key)

    # Extract arbitrary sheeetz-namespace keys not already mapped
    sheeetz_prefix = f"{{{SHEEETZ_NS}}}"
    mapped_sheeetz_keys = {k.lower() for k in RAW_TO_CORE_MAP if k.startswith(sheeetz_prefix)}
    for raw_key, value in raw_meta.items():
        if raw_key.startswith(sheeetz_prefix) and raw_key.lower() not in mapped_sheeetz_keys:
            field_name = raw_key[len(sheeetz_prefix):]
            if field_name and field_name != "pages" and value.strip():
                core[field_name] = value.strip()

    return core


def write_pdf_metadata(pdf_bytes: bytes, core_meta: dict[str, str]) -> bytes:
    """Write core metadata fields to the sheeetz XMP namespace in a PDF.

    Only writes non-blank values. Removes sheeetz keys for blank/missing fields.
    All other metadata (dc:, docinfo, etc.) is left untouched.
    Returns the modified PDF bytes.
    """
    buf = io.BytesIO(pdf_bytes)
    with pikepdf.open(buf) as pdf:
        with pdf.open_metadata() as xmp:
            for field_key, value_raw in core_meta.items():
                if field_key == "pages":
                    continue  # pages is auto-derived, never write it
                ns_key = f"{{{SHEEETZ_NS}}}{field_key}"
                value = value_raw.strip() if isinstance(value_raw, str) else str(value_raw).strip()
                if value:
                    xmp[ns_key] = value
                else:
                    # Remove the key if blank
                    try:
                        del xmp[ns_key]
                    except KeyError:
                        pass

        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()
