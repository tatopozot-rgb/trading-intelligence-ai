"""
Append-only audit log. Never truncate, never modify a written entry.
Rotates daily: audit_YYYY-MM-DD.jsonl in the configured directory.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class _JSONEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        if is_dataclass(o) and not isinstance(o, type):
            return asdict(o)
        return super().default(o)


class AuditLog:
    """Append-only JSONL audit log, rotated daily."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _current_file(self, now: datetime | None = None) -> Path:
        now = now or datetime.now(timezone.utc)
        return self.directory / f"audit_{now.strftime('%Y-%m-%d')}.jsonl"

    def append(self, record: dict) -> None:
        """Append one record as a single JSON line. An IO failure (disk
        full, permissions, directory removed) is never silently lost: it
        is logged at CRITICAL first, then re-raised as RuntimeError —
        callers get a clean, well-typed exception rather than a raw
        OSError, but the failure is never swallowed. Whether a caller
        should treat a failed audit write as reason to halt (vs. degrade)
        is a risk-policy question, not this module's to decide."""
        record = dict(record)
        record.setdefault("logged_at", datetime.now(timezone.utc).isoformat())
        line = json.dumps(record, cls=_JSONEncoder, sort_keys=True)
        path = self._current_file()
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as error:
            logger.critical("AuditLog failed to write to %s: %s", path, error)
            raise RuntimeError(f"AuditLog failed to write to {path}") from error

    def read_all(self, date: str | None = None) -> list[dict]:
        """Read all entries for a given date (YYYY-MM-DD), or today's file."""
        if date is not None:
            path = self.directory / f"audit_{date}.jsonl"
        else:
            path = self._current_file()
        if not path.exists():
            return []
        entries = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries
