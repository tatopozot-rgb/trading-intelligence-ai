"""Offline unit tests for review orchestration; never invokes a real harness."""
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import subprocess
import json

spec = importlib.util.spec_from_file_location("review_runner", Path(__file__).with_name("run_acceptance_review.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReviewRunnerTests(unittest.TestCase):
    def test_research_scope_includes_new_lifecycle_and_reservation_gates(self):
        names = [spec[0] for spec in module.SCOPES["research"]]
        self.assertEqual(names.count("test_runner_lifecycle_review.py"), 1)
        self.assertEqual(names.count("test_reservation_review.py"), 1)

    def test_json_roundtrips_unicode_on_legacy_windows_console(self):
        original = {"output": "Unicode: \u03a9 \ufffd \u2192"}
        encoded = module.serialize_report(original)
        self.assertTrue(all(ord(c) < 128 for c in encoded))
        self.assertEqual(json.loads(encoded.encode("cp1252").decode("cp1252")), original)

    def test_no_scopes_is_not_success(self):
        report = module.build_report({}, Path("."), 1)
        self.assertFalse(report["all_selected_pass"])
        self.assertFalse(report["end_to_end_certified"])
        self.assertTrue(all(x["status"] == "NOT_RUN" for x in report["results"]))

    def test_other_scopes_are_not_silently_passed(self):
        report = module.build_report({"halt": Path(".")}, Path("."), 1,
                                     suite_runner=lambda scope, spec, *a: {"scope": scope, "kind": spec[1], "status": "PASS"})
        self.assertTrue(report["all_selected_pass"])
        self.assertEqual(sum(r["status"] == "NOT_RUN" for r in report["results"]), 3)
        self.assertFalse(report["end_to_end_certified"])

    def test_failure_prevents_success(self):
        report = module.build_report({"sync": Path(".")}, Path("."), 1,
                                     suite_runner=lambda *a: {"status": "FAIL"})
        self.assertFalse(report["all_selected_pass"])

    def test_missing_sources_never_run_subprocess(self):
        def forbidden(*args, **kwargs):
            self.fail("must not start subprocess when files are missing")
        with tempfile.TemporaryDirectory() as directory:
            result = module.run_suite("halt", ("missing.py", "acceptance", ["missing-source.py"]),
                                      Path(directory), Path(directory), 1, runner=forbidden)
        self.assertEqual(result["status"], "ERROR")

    def test_source_and_harness_are_hashed_and_timeout_is_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Isolated test fixtures only, not project-source editing.
            (root / "fixture.py").write_text("fixture", encoding="utf-8")
            def timeout(*args, **kwargs):
                raise subprocess.TimeoutExpired("fixture", 1)
            result = module.run_suite("halt", ("fixture.py", "acceptance", ["fixture.py"]),
                                      root, root, 1, runner=timeout)
            self.assertEqual(result["status"], "ERROR")
            self.assertIn("TimeoutExpired", result["error"])
            self.assertEqual(result["source_sha256"]["fixture.py"], result["harness_sha256"])
            success = module.run_suite("halt", ("fixture.py", "acceptance", ["fixture.py"]),
                                       root, root, 1,
                                       runner=lambda *a, **kw: SimpleNamespace(returncode=0, stdout="ok", stderr=""))
            self.assertEqual(success["status"], "PASS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
