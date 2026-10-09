import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import publish_live_reports as P  # noqa: E402


def _state(tmp_path, sid="20261009T032500"):
    s = tmp_path / "state"
    (s / "engine").mkdir(parents=True)
    (s / "session.json").write_text(json.dumps({"session_id": sid}))
    (s / "status.json").write_text('{"status": "RUNNING"}')
    (s / "reporte_inicio_20261009T0325.md").write_text("# INICIO")
    (s / "AVISO.txt").write_text("AVISO")
    for private in ("orders.json", "meta.json", "OPERATOR.lock", "notas.md"):
        (s / private).write_text("x")
    (s / "engine" / "paper.json").write_text("{}")
    return s


def test_only_reports_status_and_aviso_are_published(tmp_path):
    s = _state(tmp_path)
    copied = P.copy_reports(s, tmp_path / "pub")
    assert sorted(p.name for p in copied) == ["AVISO.txt", "reporte_inicio_20261009T0325.md", "status.json"]
    assert copied[0].parent == tmp_path / "pub" / "docs" / "live_reports" / "20261009T032500"
    assert P.copy_reports(s, tmp_path / "pub") == []  # unchanged: nothing to commit
    (s / "status.json").write_text('{"status": "WAITING_OWNER"}')
    assert [p.name for p in P.copy_reports(s, tmp_path / "pub")] == ["status.json"]


def test_a_strange_session_id_never_becomes_a_path(tmp_path):
    with pytest.raises(ValueError):
        P.copy_reports(_state(tmp_path, sid="../../etc"), tmp_path / "pub")


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_publishes_to_its_own_branch_in_a_separate_clone(tmp_path, monkeypatch):
    origin = tmp_path / "origin.git"
    git("init", "-q", "--bare", str(origin))
    work = tmp_path / "work"
    git("clone", "-q", str(origin), str(work))
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init", cwd=work)
    git("push", "-q", "origin", "HEAD", cwd=work)
    s = _state(tmp_path)
    monkeypatch.chdir(work)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "t")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")
    pub = tmp_path / "pub"
    assert P.main(["--state", str(s), "--repo", str(pub)]) == 0
    files = git("ls-tree", "-r", "--name-only", P.BRANCH, cwd=origin).stdout.split()
    assert "docs/live_reports/20261009T032500/status.json" in files and not any("orders" in f for f in files)
    (s / "status.json").write_text('{"status": "STOPPED"}')
    assert P.main(["--state", str(s), "--repo", str(pub)]) == 0  # existing clone, second commit
    assert git("rev-list", "--count", P.BRANCH, cwd=origin).stdout.strip() == "3"
    assert git("status", "--short", cwd=work).stdout == ""  # the operator's checkout is untouched
