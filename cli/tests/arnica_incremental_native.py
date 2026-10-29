"""Exercise the Arnica incremental scan protocol with the real CLI and core.

Usage: python arnica_incremental_native.py --source <fork checkout> --python <python>
"""

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path


def run(source: Path, python: str) -> None:
    with tempfile.TemporaryDirectory(prefix="arnica-opengrep-") as directory:
        work = Path(directory)
        repo = work / "repo"
        repo.mkdir()
        (work / "config").mkdir()
        env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "en_US.UTF-8",
            "PYTHONPATH": str(source / "cli/src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "SEMGREP_LOG_FILE": str(work / "scanner.log"),
            "SEMGREP_SETTINGS_FILE": str(work / "settings.yml"),
            "XDG_CONFIG_HOME": str(work / "config"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "SEMGREP_SEND_METRICS": "off",
        }

        def git(*args: str) -> None:
            subprocess.run(
                ["git", *args],
                cwd=repo,
                env=env,
                check=True,
                capture_output=True,
                timeout=15,
            )

        def write(path: str, contents: str) -> None:
            file = repo / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(contents)

        git("init", "--quiet")
        rules_path = work / "rules.json"
        rules = [
            {
                "id": "eval",
                "languages": ["python"],
                "message": "eval",
                "severity": "ERROR",
                "pattern": "eval($X)",
                "options": {"timeout": 5.0},
            }
        ]
        rules_path.write_text(json.dumps({"rules": rules}))
        count = 0
        cli = [python, str(source / "cli/src/semgrep/console_scripts/pysemgrep.py")]
        help_result = subprocess.run(
            cli + ["scan", "--help"],
            cwd=repo,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert "--arnica-incremental-input" in help_result.stdout
        assert "--arnica-incremental-output" in help_result.stdout

        def scan(baseline=None, config_hash="a" * 64, native=True, extra=(), baseline_report=None, expected_exit_codes=(0, 1)):
            nonlocal count
            count += 1
            input_path = work / f"input-{count}.json"
            manifest_path = work / f"manifest-{count}.json"
            report_path = work / f"report-{count}.json"
            payload = {"schemaVersion": 1, "configHash": config_hash}
            if baseline:
                warning_paths = set()
                for error in (baseline_report or {}).get("errors", []):
                    warning_paths.add(error["path"])
                    warning_paths.update(span["file"] for span in error.get("spans", []))
                payload["baseline"] = {
                    "units": [
                        {"path": unit["path"], "key": unit["key"]}
                        for unit in baseline["units"]
                        if unit["path"] not in warning_paths
                    ],
                }
            input_path.write_text(json.dumps(payload))
            command = cli + [
                "scan",
                "--config",
                str(rules_path),
                "--json",
                "--output",
                str(report_path),
                "--disable-version-check",
                "--no-rewrite-rule-ids",
                "--error",
                "--allow-rule-timeout-control",
                "--timeout-threshold",
                "0",
                "--jobs",
                "1",
            ]
            if native:
                command.extend(
                    [
                        "--arnica-incremental-input",
                        str(input_path),
                        "--arnica-incremental-output",
                        str(manifest_path),
                    ]
                )
            completed = subprocess.run(
                command + list(extra) + ["."],
                cwd=repo,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if completed.returncode not in expected_exit_codes:
                raise AssertionError(completed.stderr[-6000:])
            report = json.loads(report_path.read_text())
            manifest = (
                json.loads(manifest_path.read_text())
                if manifest_path.exists()
                else None
            )
            if manifest:
                assert (
                    manifest["reportSha256"]
                    == hashlib.sha256(report_path.read_bytes()).hexdigest()
                )
            return report, manifest

        def merged(previous, fresh, manifest):
            reused = {
                unit["path"]
                for unit in manifest["units"]
                if unit["disposition"] == "reused"
            }
            return sorted(
                [value for value in previous if value["path"] in reused]
                + fresh["results"],
                key=lambda value: (
                    value["path"],
                    value["start"]["offset"],
                    value["check_id"],
                ),
            )

        def check_full(results, extra=()):
            full, _ = scan(native=False, extra=extra)
            assert results == sorted(
                full["results"],
                key=lambda value: (
                    value["path"],
                    value["start"]["offset"],
                    value["check_id"],
                ),
            ), (results, full)
            return full

        def check_merged_report(previous, fresh, manifest, extra=()):
            results = merged(previous["results"], fresh, manifest)
            full = check_full(results, extra)
            scanned = sorted(unit["path"] for unit in manifest["units"])
            assert scanned == sorted(full["paths"]["scanned"])
            assert sorted(json.dumps(error, sort_keys=True) for error in fresh["errors"]) == sorted(
                json.dumps(error, sort_keys=True) for error in full["errors"]
            ), (fresh["errors"], full["errors"])
            return {**fresh, "results": results, "paths": {"scanned": scanned}}

        write("a.py", "eval(first)\n")
        write("b.py", "print('prefilter negative')\n")
        write("unknown.txt", "eval(unselected)\n")
        write("script", "#!/usr/bin/env python\neval(script)\n")
        (repo / "script").chmod(0o755)
        write(".semgrepignore", ":include policy/ignored.txt\n")
        git("add", ".")
        first, baseline = scan()
        assert baseline and baseline["mode"] == "incremental"
        dispositions = {unit["path"]: unit["disposition"] for unit in baseline["units"]}
        assert dispositions["b.py"] == "completed"
        assert "unknown.txt" not in dispositions
        assert dispositions["script"] == "completed"
        check_full(merged([], first, baseline))

        no_op, no_op_manifest = scan(baseline)
        assert no_op_manifest and not no_op["results"] and not no_op["paths"]["scanned"]
        assert {
            unit["path"]
            for unit in no_op_manifest["units"]
            if unit["disposition"] == "reused"
        } == {"a.py", "b.py", "script"}
        current = merged(first["results"], no_op, no_op_manifest)
        check_full(current)

        write("policy/ignored.txt", "a.py\n")
        git("add", ".")
        ignored, ignored_manifest = scan(no_op_manifest)
        assert ignored_manifest and not ignored["paths"]["scanned"]
        assert all(unit["path"] != "a.py" for unit in ignored_manifest["units"])
        current = merged(current, ignored, ignored_manifest)
        check_full(current)

        write("policy/ignored.txt", "")
        write("c.py", "eval(new)\n")
        (repo / "script").unlink()
        git("add", "-A")
        changed, changed_manifest = scan(ignored_manifest)
        assert changed_manifest and set(changed["paths"]["scanned"]) == {"a.py", "c.py"}
        current = merged(current, changed, changed_manifest)
        check_full(current)

        config_changed, config_manifest = scan(changed_manifest, config_hash="b" * 64)
        assert config_manifest and set(config_changed["paths"]["scanned"]) == {
            "a.py",
            "b.py",
            "c.py",
        }
        check_full(config_changed["results"])

        rules[0]["pattern"] = "print($X)"
        rules_path.write_text(json.dumps({"rules": rules}))
        changed_rules, rules_manifest = scan(config_manifest, config_hash="b" * 64)
        assert rules_manifest and set(changed_rules["paths"]["scanned"]) == {
            "a.py",
            "b.py",
            "c.py",
        }
        check_full(changed_rules["results"])

        def assignment(analyzer, rule_ids):
            return hashlib.sha256(
                json.dumps(
                    {"analyzer": analyzer, "rules": sorted(rule_ids)},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()

        rules.extend(
            [
                {**rules[0], "id": "only-a", "pattern": "eval($X)", "paths": {"include": ["a.py"]}},
                {
                    "id": "regex-eval",
                    "languages": ["regex"],
                    "message": "eval",
                    "severity": "ERROR",
                    "pattern-regex": r"eval\(",
                    "paths": {"include": ["a.py"]},
                },
            ]
        )
        rules_path.write_text(json.dumps({"rules": rules}))
        grouped, grouped_manifest = scan(rules_manifest, config_hash="b" * 64)
        assert grouped_manifest and grouped_manifest["mode"] == "incremental"
        assignments = {unit["path"]: unit["assignments"] for unit in grouped_manifest["units"]}
        assert assignments["a.py"] == sorted(
            [assignment("python", ["eval", "only-a"]), assignment("regex", ["regex-eval"])]
        )
        assert assignments["b.py"] == assignments["c.py"] == [assignment("python", ["eval"])]
        check_full(merged([], grouped, grouped_manifest))

        grouped_no_op, grouped_no_op_manifest = scan(grouped_manifest, config_hash="b" * 64)
        assert grouped_no_op_manifest and not grouped_no_op["paths"]["scanned"]
        assert merged(grouped["results"], grouped_no_op, grouped_no_op_manifest) == sorted(
            grouped["results"], key=lambda value: (value["path"], value["start"]["offset"], value["check_id"])
        )

        rules[1]["id"] = "renamed-a"
        rules_path.write_text(json.dumps({"rules": rules}))
        renamed, renamed_manifest = scan(grouped_no_op_manifest, config_hash="b" * 64)
        assert renamed_manifest and set(renamed["paths"]["scanned"]) == {"a.py", "b.py", "c.py"}
        assert next(unit["assignments"] for unit in renamed_manifest["units"] if unit["path"] == "a.py") == sorted(
            [assignment("python", ["eval", "renamed-a"]), assignment("regex", ["regex-eval"])]
        )
        check_full(merged([], renamed, renamed_manifest))
        del rules[1:]

        rules[0]["options"]["taint_assume_safe_comparisons"] = True
        rules_path.write_text(json.dumps({"rules": rules}))
        unsupported, unsupported_manifest = scan(rules_manifest, config_hash="b" * 64)
        assert unsupported_manifest and unsupported_manifest["mode"] == "full"
        assert unsupported_manifest["fallbackReason"] == "unsupported_rules"
        assert set(unsupported["paths"]["scanned"]) == {"a.py", "b.py", "c.py"}
        check_full(unsupported["results"])

        rules[0]["options"].pop("taint_assume_safe_comparisons")
        taint_rule = {
            "id": "taint",
            "languages": ["python"],
            "message": "taint",
            "severity": "ERROR",
            "mode": "taint",
            "pattern-sources": [{"pattern": "source($LABEL)"}],
            "pattern-sinks": [{"pattern": "sink($LABEL, $VALUE)"}],
            "options": {
                "timeout": 5.0,
                "taint_fixpoint_timeout": 0.4,
                "interfile": True,
                "taint_unify_mvars": True,
            },
        }
        rules_path.write_text(json.dumps({"rules": [taint_rule]}))
        write(
            "tainted.py",
            'def f():\n    value = source("same")\n'
            '    sink("same", value)\n    sink("different", value)\n',
        )
        write("taint_source.py", 'def remote_source():\n    return source("same")\n')
        write(
            "taint_consumer.py",
            "from taint_source import remote_source\n"
            'def f():\n    sink("same", remote_source())\n',
        )
        git("add", ".")
        taint, taint_manifest = scan()
        assert (
            taint_manifest
            and taint_manifest["mode"] == "incremental"
            and len(taint["results"]) == 1
        )
        taint_reused, taint_reused_manifest = scan(taint_manifest)
        assert taint_reused_manifest and not taint_reused["paths"]["scanned"]
        check_full(merged(taint["results"], taint_reused, taint_reused_manifest))

        write("taint_source.py", 'def remote_source():\n    return "safe"\n')
        dependency_changed, dependency_manifest = scan(taint_reused_manifest)
        assert dependency_manifest and dependency_manifest["mode"] == "incremental"
        assert dependency_changed["paths"]["scanned"] == ["taint_source.py"]
        assert next(
            unit["disposition"]
            for unit in dependency_manifest["units"]
            if unit["path"] == "taint_consumer.py"
        ) == "reused"
        check_full(merged(taint["results"], dependency_changed, dependency_manifest))

        taint_rule["options"]["taint_unify_mvars"] = False
        rules_path.write_text(json.dumps({"rules": [taint_rule]}))
        unification_changed, unification_manifest = scan(dependency_manifest)
        assert unification_manifest and unification_manifest["mode"] == "incremental"
        assert len(unification_changed["results"]) == 2
        assert all(
            unit["disposition"] != "reused" for unit in unification_manifest["units"]
        )
        check_full(unification_changed["results"])

        rules[0]["pattern"] = "eval($X)"
        rules.append({**rules[0], "id": "second-eval"})
        rules_path.write_text(json.dumps({"rules": rules}))
        match_limit = ("--max-match-per-file", "1")
        limited, limited_manifest = scan(extra=match_limit)
        assert limited["errors"] and limited_manifest
        limited_report = check_merged_report({"results": []}, limited, limited_manifest, match_limit)
        limited_again, limited_again_manifest = scan(limited_manifest, extra=match_limit, baseline_report=limited_report)
        assert limited_again_manifest and set(limited_again["paths"]["scanned"]) == {
            error["path"] for error in limited["errors"]
        }
        check_merged_report(limited_report, limited_again, limited_again_manifest, match_limit)

        rules.pop()
        rules[0]["pattern"] = "eval($X"
        rules_path.write_text(json.dumps({"rules": rules}))
        invalid_rule, invalid_rule_manifest = scan(expected_exit_codes=(2,))
        assert any(error["level"] == "error" for error in invalid_rule["errors"])
        assert invalid_rule_manifest is None

        rules[0]["pattern"] = "eval($X)"
        rules_path.write_text(json.dumps({"rules": rules}))
        clean, clean_manifest = scan()
        write("a.py", "def broken(\neval(x)\n")
        malformed, malformed_manifest = scan(clean_manifest, baseline_report=clean)
        assert malformed_manifest and malformed["paths"]["scanned"] == ["a.py"]
        assert malformed["errors"] and not malformed["results"]
        current_report = check_merged_report(clean, malformed, malformed_manifest)
        assert any(result["path"] == "c.py" for result in current_report["results"])

        repeated, repeated_manifest = scan(malformed_manifest, baseline_report=current_report)
        assert repeated_manifest and repeated["paths"]["scanned"] == ["a.py"]
        assert repeated["errors"] and not repeated["results"]
        current_report = check_merged_report(current_report, repeated, repeated_manifest)

        write("a.py", "eval(recovered)\n")
        recovered, recovered_manifest = scan(repeated_manifest, baseline_report=current_report)
        assert recovered_manifest and recovered["paths"]["scanned"] == ["a.py"]
        assert not recovered["errors"] and recovered["results"]
        current_report = check_merged_report(current_report, recovered, recovered_manifest)

        recovered_no_op, recovered_no_op_manifest = scan(recovered_manifest, baseline_report=current_report)
        assert recovered_no_op_manifest and not recovered_no_op["paths"]["scanned"]
        current_report = check_merged_report(current_report, recovered_no_op, recovered_no_op_manifest)

        rules.append({**rules[0], "id": "js-eval", "languages": ["javascript"]})
        rules_path.write_text(json.dumps({"rules": rules}))
        write("stable.js", "eval(stable);\n")
        write("partial.js", "export opaque type Reason = 0 | 1;\neval(warned);\n")
        git("add", ".")
        partial, partial_manifest = scan(recovered_no_op_manifest, baseline_report=current_report)
        assert partial_manifest and partial["errors"]
        assert any(result["path"] == "partial.js" for result in partial["results"])
        current_report = check_merged_report(current_report, partial, partial_manifest)

        partial_repeated, partial_repeated_manifest = scan(partial_manifest, baseline_report=current_report)
        assert partial_repeated_manifest and partial_repeated["paths"]["scanned"] == ["partial.js"]
        assert partial_repeated["errors"] and partial_repeated["results"]
        current_report = check_merged_report(current_report, partial_repeated, partial_repeated_manifest)

        (repo / "partial.js").rename(repo / "renamed.js")
        git("add", "-A")
        renamed_warning, renamed_warning_manifest = scan(partial_repeated_manifest, baseline_report=current_report)
        assert renamed_warning_manifest and renamed_warning["paths"]["scanned"] == ["renamed.js"]
        assert {error["path"] for error in renamed_warning["errors"]} == {"renamed.js"}
        current_report = check_merged_report(current_report, renamed_warning, renamed_warning_manifest)

        write("policy/ignored.txt", "renamed.js\n")
        ignored_warning, ignored_warning_manifest = scan(renamed_warning_manifest, baseline_report=current_report)
        assert ignored_warning_manifest and not ignored_warning["paths"]["scanned"]
        assert not ignored_warning["errors"]
        current_report = check_merged_report(current_report, ignored_warning, ignored_warning_manifest)

        (repo / "renamed.js").unlink()
        git("add", "-A")
        deleted_warning, deleted_warning_manifest = scan(ignored_warning_manifest, baseline_report=current_report)
        assert deleted_warning_manifest and not deleted_warning["paths"]["scanned"]
        current_report = check_merged_report(current_report, deleted_warning, deleted_warning_manifest)
        assert all(result["path"] != "renamed.js" for result in current_report["results"])

        rules.pop()
        rules_path.write_text(json.dumps({"rules": rules}))

        empty_rules, empty_rules_manifest = scan(extra=("--exclude-rule", "eval"))
        assert empty_rules_manifest and not empty_rules["results"]
        assert not empty_rules["paths"]["scanned"]
        assert empty_rules_manifest["units"] == []

        for path in repo.glob("*.py"):
            path.unlink()
        git("add", "-A")
        no_targets, no_targets_manifest = scan()
        assert no_targets_manifest and not no_targets["results"]
        assert not no_targets["paths"]["scanned"]
        assert no_targets_manifest["units"] == []

        write("a.py", "eval(excluded)\n")
        write("denied.py", "eval(denied)\n")
        git("add", ".")
        readable, readable_manifest = scan()
        assert readable_manifest and len(readable["results"]) == 2
        (repo / "denied.py").chmod(0)
        try:
            excluded, excluded_manifest = scan(
                readable_manifest, extra=("--exclude", "a.py")
            )
            assert excluded_manifest and not excluded["paths"]["scanned"]
            assert excluded_manifest["units"] == []
        finally:
            (repo / "denied.py").chmod(0o644)
        print(
            json.dumps(
                {
                    "cli_invocations": count,
                    "status": "passed",
                    "checks": [
                        "full-result parity",
                        "prefilter-negative completion",
                        "no unit for unassigned files",
                        "executable shebang discovery",
                        "zero-dispatch reuse",
                        "indirect ignore change",
                        "new/deleted files",
                        "same-head config/rule changes",
                        "shared and distinct native assignments",
                        "resolved rule ID changes at unchanged plan indexes",
                        "whole-ruleset fallback",
                        "combined match cap warning rescan and parity",
                        "hard rule error rejection",
                        "zero-finding parse warnings with completion receipts",
                        "warning-file rescan with clean-file reuse",
                        "partial-parser findings and diagnostic parity",
                        "parser recovery restores reuse",
                        "renamed/excluded/deleted diagnostic paths",
                        "final report digest",
                        "production timeout options",
                        "taint-rule reuse",
                        "OSS interfile option and dependency-change parity",
                        "metavariable-unification option invalidation",
                        "visible capability flags",
                        "zero resolved rules",
                        "zero native targets",
                        "no units for excluded/read-denied files",
                    ],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--python", required=True)
    arguments = parser.parse_args()
    run(arguments.source.resolve(), arguments.python)
