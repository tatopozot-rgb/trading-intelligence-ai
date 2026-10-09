"""Publishes the live session's reports to GitHub so the Leader and GPT Work can audit it.

Run it on the owner's PC (by hand or from a scheduled task every hour):

    python tools/publish_live_reports.py --state live_runs/current --repo ..\\live-reports-repo

It copies ONLY the human-readable outputs of the session (status.json, the start/mid/final
reports and AVISO.txt) into docs/live_reports/<session id>/ of a SEPARATE clone on the
branch `live-reports`, commits and pushes. It never touches the operator's own checkout,
the order journal, the session ledger or anything with a key. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Sequence

BRANCH = "live-reports"
PUBLISHED = re.compile(r"^(status\.json|AVISO\.txt|reporte_(inicio|medio|final)_\d{8}T\d{4}\.md)$")
_SESSION_ID = re.compile(r"^[0-9A-Za-z_-]{1,40}$")


def session_id(state: Path) -> str:
    data = json.loads((state / "session.json").read_text(encoding="utf-8"))
    sid = str(data.get("session_id", ""))
    if not _SESSION_ID.fullmatch(sid):
        raise ValueError("unexpected session id")
    return sid


def files_to_publish(state: Path) -> list[Path]:
    """Only the reports and the status: never orders.json, session.json, meta.json or engine/."""
    return sorted(p for p in state.iterdir() if p.is_file() and PUBLISHED.fullmatch(p.name))


def copy_reports(state: Path, target_root: Path) -> list[Path]:
    """Copies what changed into target_root/docs/live_reports/<session>/. Returns the copies."""
    dest = target_root / "docs" / "live_reports" / session_id(state)
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for src in files_to_publish(state):
        out = dest / src.name
        if not out.exists() or out.read_bytes() != src.read_bytes():
            shutil.copyfile(src, out)
            copied.append(out)
    return copied


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def ensure_clone(repo: Path, source: Path) -> None:
    if (repo / ".git").exists():
        _git(repo, "fetch", "-q", "origin")
        if _git(repo, "ls-remote", "--heads", "origin", BRANCH).strip():
            _git(repo, "checkout", "-q", "-B", BRANCH, f"origin/{BRANCH}")
        return
    url = _git(source, "remote", "get-url", "origin").strip()
    subprocess.run(["git", "clone", "-q", url, str(repo)], check=True)
    if _git(repo, "ls-remote", "--heads", "origin", BRANCH).strip():
        _git(repo, "checkout", "-q", "-B", BRANCH, f"origin/{BRANCH}")
    else:
        _git(repo, "checkout", "-q", "-b", BRANCH)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Publish the live session's reports (no keys, no ledgers).")
    parser.add_argument("--state", type=Path, default=Path("live_runs/current"))
    parser.add_argument("--repo", type=Path, required=True, help="a separate clone used only for publishing")
    args = parser.parse_args(argv)
    if not (args.state / "session.json").exists():
        print("sin sesión: nada que publicar")
        return 0
    ensure_clone(args.repo, Path.cwd())
    copied = copy_reports(args.state, args.repo)
    if not copied:
        print("sin cambios")
        return 0
    _git(args.repo, "add", "docs/live_reports")
    _git(args.repo, "commit", "-q", "-m", f"Live reports: session {session_id(args.state)} ({len(copied)} file(s))")
    _git(args.repo, "push", "-q", "origin", BRANCH)
    print(f"publicado: {len(copied)} archivo(s) en la rama {BRANCH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
