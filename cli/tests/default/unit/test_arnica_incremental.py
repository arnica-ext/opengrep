import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pytest

from semgrep.arnica_incremental import digest
from semgrep.arnica_incremental import IncrementalScan

pytestmark = pytest.mark.quick


class IncrementalScanTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(
            prefix="arnica-incremental-protocol-"
        )
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.input = self.root / "input.json"
        self.output = self.root / "manifest.json"
        self.report = self.root / "report.json"
        self.input.write_text(json.dumps({"schemaVersion": 1, "configHash": "a" * 64}))
        self.report.write_text(json.dumps({"results": [], "errors": []}))
        (self.root / "a.py").write_text("print(1)\n")

    def scan(self):
        scan = IncrementalScan(self.input, self.output, self.report, self.root)
        scan.configure(
            [{"id": "local", "languages": ["python"], "pattern": "eval($X)"}], True
        )
        scan.prepare(
            [{"path": "a.py", "assignment": digest({"analyzer": "python", "rules": ["local"]})}]
        )
        return scan

    def scan_assignments(
        self, assignments, baseline=None, analyzer="python", pattern="eval($X)"
    ):
        payload = {"schemaVersion": 1, "configHash": "a" * 64}
        if baseline:
            payload["baseline"] = {
                "units": [
                    {"path": unit["path"], "key": unit["key"]}
                    for unit in baseline["units"]
                ],
            }
        self.input.write_text(json.dumps(payload))
        scan = IncrementalScan(self.input, self.output, self.report, self.root)
        scan.configure(
            [
                {"id": name, "languages": ["python"], "pattern": pattern}
                for name in ("first", "second")
            ],
            True,
        )
        dispatched = scan.prepare(
            [{"path": "a.py", "assignment": digest({"analyzer": analyzer, "rules": sorted(assignments)})}]
        )
        scan.complete_core(list(dispatched), [], [], [])
        scan.seal([])
        return json.loads(self.output.read_text())

    def test_should_bound_manifest_size_when_many_files_share_many_rules(self):
        rules = [
            {
                "id": f"python.security.example.long-rule-name-{index}",
                "languages": ["python"],
                "pattern": "eval($X)",
            }
            for index in range(250)
        ]
        paths = [f"file-{index}.py" for index in range(1000)]
        for path in paths:
            (self.root / path).write_text("x = 1\n")
        scan = IncrementalScan(self.input, self.output, self.report, self.root)
        scan.configure(rules, True)

        assignment = digest({"analyzer": "python", "rules": sorted(rule["id"] for rule in rules)})
        scan.prepare(
            [{"path": path, "assignment": assignment} for path in paths]
        )
        scan.complete_core(paths, [], [], [])
        scan.seal([])

        self.assertEqual(len(json.loads(self.output.read_text())["units"]), len(paths))
        self.assertLess(self.output.stat().st_size, 1024 * 1024)

    def test_should_reuse_identical_assignments_regardless_of_rule_order(self):
        baseline = self.scan_assignments(["first", "second"])

        repeated = self.scan_assignments(["second", "first"], baseline)

        self.assertEqual(repeated["units"][0]["disposition"], "reused")

    def test_should_rescan_when_assigned_rules_or_analyzer_change(self):
        baseline = self.scan_assignments(["first", "second"])

        for assignments, analyzer in [
            (["first"], "python"),
            (["first", "second"], "generic"),
        ]:
            with self.subTest(assignments=assignments, analyzer=analyzer):
                changed = self.scan_assignments(assignments, baseline, analyzer)

                self.assertEqual(changed["units"][0]["disposition"], "completed")

    def test_should_rescan_when_rule_bodies_change_with_the_same_assignments(self):
        baseline = self.scan_assignments(["first", "second"])

        changed = self.scan_assignments(["first", "second"], baseline, pattern="print($X)")

        self.assertEqual(changed["units"][0]["disposition"], "completed")

    def test_should_require_all_targets_and_no_errors_or_skips(self):
        for scanned, errors, skipped_rules, skipped_targets, final_errors in [
            ([], [], [], [], []),
            (["a.py", "a.py"], [], [], [], []),
            (["a.py"], ["timeout"], [], [], []),
            (["a.py"], [], ["missing plugin"], [], []),
            (["a.py"], [], [], ["partial analysis"], []),
            (["a.py"], [], [], [], ["formatting error"]),
        ]:
            with self.subTest(
                scanned=scanned,
                errors=errors,
                skipped_rules=skipped_rules,
                skipped_targets=skipped_targets,
                final_errors=final_errors,
            ):
                scan = self.scan()
                scan.complete_core(scanned, errors, skipped_rules, skipped_targets)
                scan.seal(final_errors)
                self.assertFalse(self.output.exists())

    def test_should_preserve_scoped_warnings_and_findings_in_the_certified_report(self):
        (self.root / "b.py").write_text("eval(value)\n")
        scan = IncrementalScan(self.input, self.output, self.report, self.root)
        scan.configure([], True)
        scan.prepare(
            [{"path": path, "assignment": "python"} for path in ("a.py", "b.py")]
        )
        warning = {
            "level": "warn",
            "type": "AnUnrecognizedWarningName",
            "path": str(scan.root / "a.py"),
            "spans": [{"file": "a.py"}, {"file": "b.py"}],
        }
        report = json.dumps({"results": [{"path": "b.py"}], "errors": [warning]})
        self.report.write_text(report)

        scan.complete_core(["a.py", "b.py"], [warning], [], [])
        scan.seal([warning])

        manifest = json.loads(self.output.read_text())
        self.assertEqual(manifest["mode"], "incremental")
        self.assertEqual(
            {unit["path"]: unit["disposition"] for unit in manifest["units"]},
            {"a.py": "completed", "b.py": "completed"},
        )
        self.assertEqual(self.report.read_text(), report)
        self.assertEqual(manifest["reportSha256"], hashlib.sha256(report.encode()).hexdigest())

    def test_should_reject_unsafe_diagnostics_from_every_source(self):
        warning = {"level": "warn", "path": "a.py"}
        for errors in [
            None,
            {},
            ["warning"],
            [{}],
            [{**warning, "level": "error"}],
            [{**warning, "level": "info"}],
            [{**warning, "path": None}],
            [{"level": "warn", "spans": [{"file": "a.py"}]}],
            [{**warning, "path": "../outside.py"}],
            [{**warning, "path": "a.py\x00"}],
            [{**warning, "path": "unscanned.py"}],
            [{**warning, "spans": None}],
            [{**warning, "spans": [None]}],
            [{**warning, "spans": [{}]}],
            [{**warning, "spans": [{"file": "a.py"}, {"file": "unscanned.py"}]}],
            [{**warning, "spans": [{"file": "../outside.py"}]}],
        ]:
            for source in ("core", "final", "report"):
                with self.subTest(errors=errors, source=source):
                    scan = self.scan()
                    self.report.write_text(json.dumps({
                        "results": [], "errors": errors if source == "report" else []
                    }))
                    scan.complete_core(["a.py"], errors if source == "core" else [], [], [])
                    scan.seal(errors if source == "final" else [])

                    self.assertFalse(self.output.exists())

    def test_should_not_certify_warning_paths_omitted_from_the_report(self):
        warning = {"level": "warn", "path": "a.py"}
        for source in ("core", "final"):
            with self.subTest(source=source):
                scan = self.scan()
                scan.complete_core(["a.py"], [warning] if source == "core" else [], [], [])
                scan.seal([warning] if source == "final" else [])

                self.assertFalse(self.output.exists())

    def test_should_require_complete_dispatch_even_with_scoped_warnings(self):
        warning = {"level": "warn", "path": "a.py"}
        self.report.write_text(json.dumps({"results": [], "errors": [warning]}))
        for scanned, skipped_rules, skipped_targets in [
            ([], [], []),
            (["a.py", "a.py"], [], []),
            (["a.py"], ["rule"], []),
            (["a.py"], [], ["target"]),
        ]:
            with self.subTest(scanned=scanned, skipped_rules=skipped_rules, skipped_targets=skipped_targets):
                scan = self.scan()
                scan.complete_core(scanned, [warning], skipped_rules, skipped_targets)
                scan.seal([warning])

                self.assertFalse(self.output.exists())

    def test_should_not_accept_warnings_for_reused_paths(self):
        scan = self.scan()
        scan.complete_core(["a.py"], [], [], [])
        scan.seal([])
        manifest = json.loads(self.output.read_text())
        self.input.write_text(json.dumps({
            "schemaVersion": 1,
            "configHash": "a" * 64,
            "baseline": {
                "units": [{"path": unit["path"], "key": unit["key"]} for unit in manifest["units"]]
            },
        }))
        reused = self.scan()
        warning = {"level": "warn", "path": "a.py"}
        self.report.write_text(json.dumps({"results": [], "errors": [warning]}))

        reused.complete_core([], [], [], [])
        reused.seal([warning])

        self.assertFalse(self.output.exists())

    def test_should_remove_an_earlier_receipt_before_a_new_attempt(self):
        self.output.write_text("old receipt")
        self.scan()
        self.assertFalse(self.output.exists())

    def test_should_publish_without_following_a_preexisting_temporary_symlink(self):
        scan = self.scan()
        scan.complete_core(["a.py"], [], [], [])
        victim = self.root / "unrelated.txt"
        victim.write_text("unchanged")
        legacy_temporary = self.root / "manifest.json.tmp"
        legacy_temporary.symlink_to(victim)

        scan.seal([])

        self.assertEqual(victim.read_text(), "unchanged")
        self.assertTrue(legacy_temporary.is_symlink())
        self.assertEqual(json.loads(self.output.read_text())["mode"], "incremental")
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.root.glob(".arnica-manifest-*.tmp")), [])

    def test_should_remove_temporary_files_when_publication_fails(self):
        scan = self.scan()
        scan.complete_core(["a.py"], [], [], [])
        self.output.mkdir()
        existing = self.output / "unrelated.txt"
        existing.write_text("unchanged")

        with self.assertRaises(OSError):
            scan.seal([])

        self.assertEqual(existing.read_text(), "unchanged")
        self.assertEqual(list(self.root.glob(".arnica-manifest-*.tmp")), [])

    def test_should_reject_an_outside_or_symlink_target(self):
        scan = IncrementalScan(self.input, self.output, self.report, self.root)
        with self.assertRaises(ValueError):
            scan.relative_path("../outside.py")
        (self.root / "link.py").symlink_to(self.root / "a.py")
        scan.configure([], True)
        with self.assertRaises(ValueError):
            scan.prepare(
                [{"path": "link.py", "assignment": digest({"analyzer": "python", "rules": ["local"]})}]
            )

    def test_should_reject_boolean_schema_versions(self):
        self.input.write_text(
            json.dumps({"schemaVersion": True, "configHash": "a" * 64})
        )
        with self.assertRaises(ValueError):
            IncrementalScan(self.input, self.output, self.report, self.root)

    def test_should_not_certify_a_report_containing_errors(self):
        scan = self.scan()
        scan.complete_core(["a.py"], [], [], [])
        self.report.write_text(json.dumps({"results": [], "errors": ["late error"]}))
        scan.seal([])
        self.assertFalse(self.output.exists())

    def test_should_fall_back_for_secret_rules_and_unknown_options(self):
        for overrides in [
            {"metadata": {"product": "secrets"}},
            {"options": {"taint_assume_safe_comparisons": True}},
            {"mode": "join"},
        ]:
            with self.subTest(overrides=overrides):
                scan = IncrementalScan(self.input, self.output, self.report, self.root)
                rule = {"id": "local", "languages": ["python"], "pattern": "eval($X)", **overrides}
                scan.configure([rule], True)
                scan.seal([])
                manifest = json.loads(self.output.read_text())
                self.assertEqual(manifest["mode"], "full")
                self.assertEqual(manifest["fallbackReason"], "unsupported_rules")
                self.assertEqual(manifest["units"], [])

    def test_should_fall_back_for_unsupported_invocations_with_reviewed_options(self):
        scan = IncrementalScan(self.input, self.output, self.report, self.root)
        scan.configure(
            [{"id": "local", "options": {"interfile": True, "taint_unify_mvars": True}}],
            False,
        )

        scan.seal([])

        manifest = json.loads(self.output.read_text())
        self.assertEqual(manifest["mode"], "full")
        self.assertEqual(manifest["fallbackReason"], "unsupported_invocation")
        self.assertEqual(manifest["units"], [])

    def test_should_reject_unknown_or_missing_input_fields(self):
        unit = {"path": "a.py", "key": "b" * 64}
        for payload in [
            {"configHash": "a" * 64},
            {"schemaVersion": 1},
            {"schemaVersion": 1, "configHash": "a" * 64, "extra": True},
            {"schemaVersion": 1, "configHash": "a" * 64, "baseline": {}},
            {"schemaVersion": 1, "configHash": "a" * 64, "baseline": {"units": [unit], "configHash": "a" * 64}},
            {"schemaVersion": 1, "configHash": "a" * 64, "baseline": {"units": [{"path": "a.py"}]}},
            {"schemaVersion": 1, "configHash": "a" * 64, "baseline": {"units": [{**unit, "disposition": "completed"}]}},
            {"schemaVersion": 1, "configHash": "a" * 64, "baseline": {"units": [unit, unit]}},
        ]:
            with self.subTest(payload=payload):
                self.input.write_text(json.dumps(payload))
                with self.assertRaises(ValueError):
                    IncrementalScan(self.input, self.output, self.report, self.root)

    def test_should_emit_units_only_for_assigned_targets_and_reuse_only_matching_keys(self):
        for path in ("b.py", "unassigned.py"):
            (self.root / path).write_text("print(1)\n")
        assignment = digest({"analyzer": "python", "rules": ["local"]})
        scan = self.scan()
        scan.complete_core(["a.py"], [], [], [])
        scan.seal([])
        key = json.loads(self.output.read_text())["units"][0]["key"]
        self.input.write_text(json.dumps({
            "schemaVersion": 1,
            "configHash": "a" * 64,
            "baseline": {"units": [{"path": "a.py", "key": key}, {"path": "b.py", "key": key}]},
        }))
        scan = IncrementalScan(self.input, self.output, self.report, self.root)
        scan.configure([{"id": "local", "languages": ["python"], "pattern": "eval($X)"}], True)

        dispatched = scan.prepare([{"path": "b.py", "assignment": assignment}])
        scan.complete_core(["b.py"], [], [], [])
        scan.seal([])

        self.assertEqual(dispatched, {"b.py"})
        self.assertEqual(
            [(unit["path"], unit["disposition"]) for unit in json.loads(self.output.read_text())["units"]],
            [("b.py", "completed")],
        )


if __name__ == "__main__":
    unittest.main()
