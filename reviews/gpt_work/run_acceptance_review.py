"""Run only existing independent review harnesses and emit source-stamped JSON.

Review utility, not an operational trading runner or an activation gate.
Each supplied source directory is imported by the already-reviewed harnesses.
Omitted scopes are NOT_RUN, never silently passed. No connector/private API calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


SCOPES = {
    "halt": [
        ("test_watchdog_review.py", "acceptance", ["paper_store.py", "config.py"]),
        ("atomicity_review.py", "experiment_not_runtime_fix", ["paper_store.py", "config.py"]),
    ],
    "research": [
        ("test_pipeline_review.py", "acceptance", ["trading_intelligence/backtesting/backtest_engine.py", "trading_intelligence/strategy/router.py", "trading_intelligence/learning/regime_performance.py"]),
        ("test_exchange_readiness_review.py", "acceptance", ["trading_intelligence/execution/binance.py", "trading_intelligence/execution/dry_run.py"]),
        ("test_paper_recovery_review.py", "acceptance", ["trading_intelligence/execution/paper.py"]),
        ("test_risk_boundaries_review.py", "acceptance", ["trading_intelligence/risk/engine.py", "trading_intelligence/risk/models.py"]),
        ("test_runner_lifecycle_review.py", "acceptance", ["trading_intelligence/execution/paper_runner.py", "trading_intelligence/execution/paper.py", "trading_intelligence/risk/engine.py"]),
        ("test_reservation_review.py", "acceptance", ["trading_intelligence/execution/paper_runner.py", "trading_intelligence/execution/paper.py", "trading_intelligence/risk/engine.py", "trading_intelligence/risk/models.py"]),
    ],
    "sync": [("test_sync_review.py", "acceptance", ["sync_agent_city.py"])],
    "city": [("agent_city_acceptance.test.mjs", "acceptance", ["lib/model.mjs", "lib/life.mjs"])],
}


def run_suite(scope: str, spec: tuple, source: Path, harness_dir: Path, timeout: float, runner=subprocess.run) -> dict:
    name, kind, files = spec
    result = {"scope": scope, "suite": name, "kind": kind, "source": str(source), "status": "ERROR"}
    required = [source / item for item in files] + [harness_dir / name]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        return {**result, "error": "Missing required files", "missing": missing}
    result["source_sha256"] = {item: hashlib.sha256((source / item).read_bytes()).hexdigest() for item in files}
    result["harness_sha256"] = hashlib.sha256((harness_dir / name).read_bytes()).hexdigest()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    if scope == "city":
        env["AGENT_CITY_REVIEW_SOURCE"] = str(source)
        command = ["node", "--test", str(harness_dir / name)]
    else:
        command = [sys.executable, "-B", str(harness_dir / name), str(source)]
    started = time.monotonic()
    try:
        process = runner(command, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
        result.update(status="PASS" if process.returncode == 0 else "FAIL", exit_code=process.returncode,
                      output=(process.stdout + process.stderr)[-24000:])
    except (OSError, subprocess.TimeoutExpired) as error:
        result["error"] = f"{type(error).__name__}: {error}"
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def build_report(sources: dict[str, Path | None], harness_dir: Path, timeout: float, suite_runner=run_suite) -> dict:
    results = []
    for scope, specs in SCOPES.items():
        source = sources.get(scope)
        if source is None:
            results.append({"scope": scope, "status": "NOT_RUN"})
        else:
            results.extend(suite_runner(scope, spec, source.resolve(), harness_dir.resolve(), timeout) for spec in specs)
    selected = [r for r in results if r["status"] != "NOT_RUN"]
    return {"schema_version": 1, "observed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "all_selected_pass": bool(selected) and all(r["status"] == "PASS" for r in selected),
            "live_activation": "NOT_AUTHORIZED_BY_THIS_REVIEW",
            "end_to_end_certified": False,
            "note": "PASS is suite-local. Atomicity experiment is not a runtime patch. No strategy edge or account eligibility certification.",
            "results": results}


def serialize_report(report: dict) -> str:
    # ASCII-safe JSON also works when a Windows parent console is cp1252.
    # Child logs are UTF-8 above; escaping preserves Unicode without dropping it.
    return json.dumps(report, ensure_ascii=True, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for scope in SCOPES:
        parser.add_argument(f"--{scope}-source", type=Path)
    parser.add_argument("--harness-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    if not (0 < args.timeout <= 60):
        parser.error("timeout must be >0 and <=60 seconds per suite")
    report = build_report({scope: getattr(args, scope + "_source") for scope in SCOPES}, args.harness_dir, args.timeout)
    print(serialize_report(report))
    return 0 if report["all_selected_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
