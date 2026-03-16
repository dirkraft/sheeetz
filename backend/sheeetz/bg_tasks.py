"""Shared base dataclass for in-memory background job state.

All background jobs (scan, organize, cleanup) extend BackgroundJob so they
share a common status/error shape and can be handled generically.

Use kw_only=True so subclasses can still declare non-default positional fields
before the inherited defaults (Python 3.10+ dataclass behaviour).
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(kw_only=True)
class BackgroundJob:
    status: Literal["running", "complete", "error"] = "running"
    error: str = ""
