"""Limited publication guard: explicit manifest or tracked working-tree files only.

No network, config execution, recursive discovery or secret-value output. This is
not a complete security audit and does not inspect historical Git commits.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import subprocess
from typing import Sequence


MAX_FILE_BYTES = 2_000_000
FORBIDDEN_DIRS = frozenset({
    ".git", ".venv", "venv", "__pycache__", "logs", "datasets", "backups",
    "solicitudes", "respuestas", ".publication", "secrets", "credentials",
})
RUNTIME_NAMES = frozenset({
    "runner_status.json", "runner.lock", "claude_request.json", "claude_request.txt",
    "market_cooldown.json", "credentials.json", "secrets.yaml", "secrets.yml",
})
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PRIVATE_KEY_MARKER", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
    ("GITHUB_TOKEN", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("MODEL_API_TOKEN", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}")),
    ("AWS_ACCESS_KEY", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("CREDENTIAL_LITERAL", re.compile(
        r"(?i)\b(?:api[_-]?key|api[_-]?secret|password|passwd|access[_-]?token|"
        r"secret[_-]?key)\b[\"']?\s*[:=]\s*[\"'][^\"'\r\n]{16,}[\"']")),
)


@dataclass(frozen=True)
class Finding:
    path: str
    reason: str


class InputError(ValueError):
    """Message is a fixed reason code, never supplied content or credentials."""


def _linked(path: Path) -> bool:
    # is_junction() is Windows-only and only exists on Python >=3.12's
    # WindowsPath; PosixPath never has it. Treat its absence as "not a
    # junction" rather than crashing on Linux/Mac or older Python.
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (is_junction is not None and is_junction())


def _root(root: Path) -> Path:
    try:
        if _linked(root) or not root.is_dir():
            raise InputError("ROOT_NOT_REGULAR_DIRECTORY")
        return root.resolve(strict=True)
    except OSError as error:
        raise InputError("ROOT_UNREADABLE") from error


def normalize_path(raw: object) -> str:
    if not isinstance(raw, str) or not raw or any(ord(c) < 32 for c in raw):
        raise InputError("INVALID_PATH")
    path = raw.replace("\\", "/")
    parts = path.split("/")
    if (PurePosixPath(path).is_absolute() or PureWindowsPath(path).drive or
            any(p in ("", ".", "..") or ":" in p or p.endswith((" ", ".")) for p in parts)):
        raise InputError("UNSAFE_PATH")
    return "/".join(parts)


def _git(root: Path, args: Sequence[str]) -> bytes:
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                                timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise InputError("GIT_UNAVAILABLE") from error
    if result.returncode != 0:
        raise InputError("GIT_COMMAND_FAILED")
    return result.stdout


def tracked_paths(root: Path) -> list[str]:
    root = _root(root)
    try:
        git_root = Path(_git(root, ["rev-parse", "--show-toplevel"]).decode("utf-8").strip())
        if git_root.resolve(strict=True) != root:
            raise InputError("ROOT_IS_NOT_GIT_TOPLEVEL")
        entries = _git(root, ["ls-files", "-z"]).decode("utf-8").split("\0")
    except (UnicodeError, OSError) as error:
        raise InputError("GIT_PATHS_UNREADABLE") from error
    return entries[:-1] if entries and entries[-1] == "" else entries


def manifest_paths(manifest: Path) -> list[str]:
    try:
        if _linked(manifest) or not manifest.is_file() or manifest.stat().st_size > MAX_FILE_BYTES:
            raise InputError("MANIFEST_INVALID_FILE")
        value = json.loads(manifest.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as error:
        raise InputError("MANIFEST_UNREADABLE") from error
    if not isinstance(value, list) or any(not isinstance(p, str) for p in value):
        raise InputError("MANIFEST_MUST_BE_PATH_LIST")
    return value


def forbidden_path(path: str) -> bool:
    parts = path.lower().split("/")
    name = parts[-1]
    return (bool(FORBIDDEN_DIRS.intersection(parts[:-1])) or name in RUNTIME_NAMES or
            name == ".env" or (name.startswith(".env.") and name != ".env.example") or
            name.startswith(("detener_", "pausa_")) or
            bool(re.search(r"\.(?:pem|key|p12|pfx|log|pyc|pyo|db|sqlite\d*)(?:-.*)?$", name)) or
            parts[:2] in (["data", "raw"], ["data", "cache"]))


def paper_config(text: str) -> bool:
    """Require unique top-level literal assignments; never import the config."""
    try:
        tree = ast.parse(text)
        values: dict[str, object] = {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for item in ast.walk(target):
                    if isinstance(item, ast.Name) and item.id in ("MODO", "USAR_DINERO_REAL"):
                        if node not in tree.body or item.id in values or isinstance(node, ast.AugAssign):
                            return False
                        values[item.id] = ast.literal_eval(node.value)
        return values.get("MODO") == "PAPER" and values.get("USAR_DINERO_REAL") is False
    except (ValueError, TypeError, SyntaxError, RecursionError):
        return False


def check_paths(root: Path, paths: Sequence[str]) -> list[Finding]:
    root = _root(root)
    findings: list[Finding] = []
    seen: set[str] = set()
    config_checked = False
    for raw in paths:
        try:
            name = normalize_path(raw)
        except InputError as error:
            findings.append(Finding("<invalid-path>", str(error)))
            continue
        if name.casefold() in seen:
            findings.append(Finding(name, "DUPLICATE_PATH"))
            continue
        seen.add(name.casefold())
        if forbidden_path(name):
            findings.append(Finding(name, "RUNTIME_OR_SECRET_PATH"))
            continue
        try:
            current = root
            for part in name.split("/"):
                current /= part
                if _linked(current):
                    raise InputError("LINKED_PATH")
            resolved = current.resolve(strict=True)
            if not resolved.is_relative_to(root) or not resolved.is_file():
                raise InputError("NOT_REGULAR_FILE_WITHIN_ROOT")
            if resolved.stat().st_size > MAX_FILE_BYTES:
                raise InputError("FILE_TOO_LARGE_FOR_GUARD")
            text = resolved.read_text(encoding="utf-8-sig")
            if "\0" in text:
                raise InputError("NON_TEXT_FILE")
        except InputError as error:
            findings.append(Finding(name, str(error)))
            continue
        except (OSError, UnicodeError):
            findings.append(Finding(name, "FILE_UNREADABLE_OR_NON_TEXT"))
            continue
        for reason, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(Finding(name, reason))
        if name == "config.py":
            config_checked = True
            if not paper_config(text):
                findings.append(Finding(name, "PAPER_CONFIG_NOT_VERIFIED"))
    if not config_checked:
        findings.append(Finding("config.py", "PAPER_CONFIG_MISSING_OR_UNREADABLE"))
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", type=Path, help="JSON list of explicit relative paths; no Git required")
    args = parser.parse_args(argv)
    try:
        paths = manifest_paths(args.manifest) if args.manifest else tracked_paths(args.root)
        findings = check_paths(args.root, paths)
    except InputError as error:
        print(f"CHECK_FAILED: {error}")
        return 2
    for finding in findings:
        print(f"{finding.path}: {finding.reason}")
    print(f"LIMITED_GUARD: files={len(paths)} findings={len(findings)}; not a complete security audit")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
