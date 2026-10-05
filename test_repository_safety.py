"""Offline fixtures for the limited publication guard; no real Git or network."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import check_repository as guard


class RepositorySafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.write("config.py", 'MODO = "PAPER"\nUSAR_DINERO_REAL = False\n')

    def write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_only_explicit_files_not_recursive(self) -> None:
        self.write(".env", "private local fixture")
        self.write("README.md", "Documentation")
        self.assertEqual(guard.check_paths(self.root, ["config.py", "README.md"]), [])

    def test_runtime_names_and_directories_rejected(self) -> None:
        for name in (".env", ".env.production", "logs/a.txt", "datasets/a.json", "backups/a.py",
                     "solicitudes/a.json", "respuestas/a.json", "runner_status.json", "runner.lock",
                     "trading.db-wal", "ledger.sqlite3", "key.pem", "id.key", "DETENER_RUNNER",
                     "PAUSA_ENTRADAS", "claude_request.txt", "data/raw/a.json", ".venv/a.py"):
            with self.subTest(name=name):
                self.assertTrue(guard.forbidden_path(name))
        self.assertFalse(guard.forbidden_path("runner_health.py"))
        self.assertFalse(guard.forbidden_path(".env.example"))

    def test_traversal_absolute_and_control_paths_rejected(self) -> None:
        for name in ("../out.py", "a/../out.py", "/tmp/x", "C:\\secret", "C:secret", "//host/share",
                     "a//b", "./file", "file\nsecret", "file:stream", "file.", "dir /file"):
            with self.subTest(name=name):
                with self.assertRaises(guard.InputError):
                    guard.normalize_path(name)
        self.assertEqual(guard.normalize_path("tools\\scan.py"), "tools/scan.py")

    def test_symlink_or_junction_rejected_without_reading(self) -> None:
        self.write("linked.py", "ignored")
        original = guard._linked
        with patch.object(guard, "_linked", side_effect=lambda p: p.name == "linked.py" or original(p)):
            found = guard.check_paths(self.root, ["config.py", "linked.py"])
        self.assertEqual(found, [guard.Finding("linked.py", "LINKED_PATH")])

    def test_missing_large_binary_and_duplicates_fail_closed(self) -> None:
        self.write("large.txt", "x" * (guard.MAX_FILE_BYTES + 1))
        self.write("binary.txt", "a\0b")
        findings = guard.check_paths(self.root, ["config.py", "config.py", "missing.py", "large.txt", "binary.txt"])
        self.assertEqual({f.reason for f in findings}, {"DUPLICATE_PATH", "FILE_UNREADABLE_OR_NON_TEXT",
                          "FILE_TOO_LARGE_FOR_GUARD", "NON_TEXT_FILE"})

    def test_secret_patterns_and_output_never_print_values(self) -> None:
        secrets = ["ghp" + "_" + "A" * 25, "sk" + "-" + "x" * 25,
                   "AKIA" + "B" * 16, "-----BEGIN " + "RSA PRIVATE KEY-----",
                   'api_key = "' + "s" * 20 + '"']
        for secret in secrets:
            with self.subTest(kind=secrets.index(secret)):
                self.write("source.py", secret)
                manifest = self.write("manifest.json", json.dumps(["config.py", "source.py"]))
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(guard.main(["--root", str(self.root), "--manifest", str(manifest)]), 1)
                self.assertNotIn(secret, output.getvalue())
                self.assertIn("source.py:", output.getvalue())

    def test_config_ast_rejects_real_missing_dynamic_and_reassigned(self) -> None:
        cases = ['MODO="REAL"\nUSAR_DINERO_REAL=False', 'MODO="PAPER"',
                 'MODO="PAPER"\nUSAR_DINERO_REAL=True', 'MODO=get_mode()\nUSAR_DINERO_REAL=False',
                 'MODO="PAPER"\nUSAR_DINERO_REAL=False\nMODO="PAPER"',
                 'if True:\n MODO="PAPER"\nUSAR_DINERO_REAL=False',
                 'MODO="PAPER"\nUSAR_DINERO_REAL=0', 'not valid python !!!']
        for text in cases:
            with self.subTest(case=cases.index(text)):
                self.assertFalse(guard.paper_config(text))
        self.assertTrue(guard.paper_config('MODO: str="PAPER"\nUSAR_DINERO_REAL: bool=False'))
        with patch("builtins.exec", side_effect=AssertionError("Must not execute")):
            self.assertTrue(guard.paper_config('MODO="PAPER"\nUSAR_DINERO_REAL=False\nraise RuntimeError()'))

    def test_config_required_in_explicit_list(self) -> None:
        self.assertEqual(guard.check_paths(self.root, []), [
            guard.Finding("config.py", "PAPER_CONFIG_MISSING_OR_UNREADABLE")])

    def test_manifest_shape_errors_and_safe_cli(self) -> None:
        for value in ({"files": ["config.py"]}, [23], "config.py"):
            manifest = self.write("manifest.json", json.dumps(value))
            with self.assertRaises(guard.InputError):
                guard.manifest_paths(manifest)
        manifest = self.write("manifest.json", json.dumps(["config.py"]))
        output = io.StringIO()
        with patch.object(guard, "_git", side_effect=AssertionError("No Git in manifest mode")), redirect_stdout(output):
            self.assertEqual(guard.main(["--root", str(self.root), "--manifest", str(manifest)]), 0)
        self.assertIn("not a complete security audit", output.getvalue())

    def test_git_exact_root_and_nul_paths(self) -> None:
        replies = [subprocess.CompletedProcess([], 0, str(self.root).encode() + b"\n", b""),
                   subprocess.CompletedProcess([], 0, b"config.py\0docs/read me.md\0", b"")]
        with patch.object(guard.subprocess, "run", side_effect=replies) as run:
            self.assertEqual(guard.tracked_paths(self.root), ["config.py", "docs/read me.md"])
        self.assertEqual(run.call_args.args[0][-2:], ["ls-files", "-z"])
        with patch.object(guard, "_git", return_value=str(self.root.parent).encode()):
            with self.assertRaisesRegex(guard.InputError, "ROOT_IS_NOT_GIT_TOPLEVEL"):
                guard.tracked_paths(self.root)

    def test_git_failure_does_not_expose_stderr(self) -> None:
        result = subprocess.CompletedProcess([], 1, b"", b"private diagnostic fixture")
        output = io.StringIO()
        with patch.object(guard.subprocess, "run", return_value=result), redirect_stdout(output):
            self.assertEqual(guard.main(["--root", str(self.root)]), 2)
        self.assertNotIn("private diagnostic fixture", output.getvalue())
        self.assertIn("GIT_COMMAND_FAILED", output.getvalue())


if __name__ == "__main__":
    unittest.main()
