"""Native root-plan reuse for the pinned Arnica OpenGrep fork."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections import Counter
from pathlib import Path
from typing import AbstractSet
from typing import Optional


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def object_value(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Expected an object")
    return value


def input_object(
    value: object, required: AbstractSet[str], optional: AbstractSet[str] = frozenset()
) -> dict:
    data = object_value(value)
    if not required <= data.keys() <= required | optional:
        raise ValueError("Unexpected incremental input fields")
    return data


def hash_value(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("Expected a lowercase SHA-256 hash")
    return value


class IncrementalScan:
    def __init__(
        self, input_path: Path, output_path: Path, report_path: Path, root: Path
    ):
        self.root = root.resolve()
        self.output_path = output_path
        self.report_path = report_path
        self.output_path.unlink(missing_ok=True)
        data = input_object(
            json.loads(input_path.read_text()), {"schemaVersion", "configHash"}, {"baseline"}
        )
        if type(data["schemaVersion"]) is not int or data["schemaVersion"] != 1:
            raise ValueError("Unsupported incremental input schema")
        self.config_hash = hash_value(data["configHash"])
        self.baseline: dict[str, str] = {}
        if "baseline" in data:
            units = input_object(data["baseline"], {"units"})["units"]
            if not isinstance(units, list):
                raise ValueError("Expected baseline units")
            for value in units:
                unit = input_object(value, {"path", "key"})
                path = self.relative_path(unit["path"])
                if path in self.baseline:
                    raise ValueError("Duplicate baseline path")
                self.baseline[path] = hash_value(unit["key"])
        self.reason: Optional[str] = None
        self.units: list[dict] = []
        self.expected: Counter[str] = Counter()
        self.prepared = False
        self.core_complete = False
        self.core_warning_paths: set[str] = set()
        self.rules_hash = ""

    def relative_path(self, value: object) -> str:
        if not isinstance(value, str) or not value or "\x00" in value:
            raise ValueError("Invalid native target path")
        path = Path(value)
        absolute = path if path.is_absolute() else self.root / path
        # Agentic Rule (ARNIE_PATH_BOUNDARY_CHECKING): Native targets must stay inside the scan root.
        relative = absolute.relative_to(self.root)
        if not relative.parts or any(part in (".", "..") for part in relative.parts):
            raise ValueError("Native target escapes scan root")
        return relative.as_posix()

    def configure(self, rules: list[dict], supported_invocation: bool) -> None:
        allowed_keys = {
            "id",
            "message",
            "severity",
            "languages",
            "mode",
            "metadata",
            "paths",
            "options",
            "pattern",
            "patterns",
            "pattern-either",
            "pattern-regex",
            "pattern-sources",
            "pattern-sinks",
            "pattern-sanitizers",
            "pattern-propagators",
            "fix",
            "fix-regex",
            "min-version",
            "max-version",
        }
        allowed_options = {
            "ac_matching",
            "commutative_boolop",
            "constant_propagation",
            "symbolic_propagation",
            "interfile",
            "taint_unify_mvars",
            "generic_ellipsis_max_span",
            "generic_comment_style",
            "generic_engine",
            "taint_intrafile",
            "taint_assume_safe_functions",
            "taint_assume_safe_indexes",
            "taint_assume_safe_booleans",
            "taint_assume_safe_numbers",
            "taint_only_propagate_through_assignments",
            "timeout",
            "taint_fixpoint_timeout",
            "dynamic_timeout",
            "dynamic_timeout_unit_kb",
            "dynamic_timeout_max_multiplier",
        }
        self.rules_hash = digest(rules)
        if not supported_invocation:
            self.reason = "unsupported_invocation"
        for rule in rules:
            options = rule.get("options", {})
            metadata = rule.get("metadata", {})
            if (
                set(rule) - allowed_keys
                or rule.get("mode", "search") not in ("search", "taint")
                or not isinstance(options, dict)
                or set(options) - allowed_options
                or not isinstance(metadata, dict)
                or metadata.get("product", "sast") != "sast"
            ):
                self.reason = "unsupported_rules"

    def prepare(self, tasks: list[dict]) -> set[str]:
        if self.prepared:
            raise ValueError(
                "Incremental protocol requires one complete native core invocation"
            )
        self.prepared = True
        selected: dict[str, list[str]] = {}
        for task in tasks:
            path = self.relative_path(task["path"])
            selected.setdefault(path, []).append(task["assignment"])
        dispatched: set[str] = set()
        for path in sorted(selected):
            assignments = sorted(set(selected[path]))
            source = self.root / path
            for component in (source, *source.parents):
                if component == self.root:
                    break
                if component.is_symlink():
                    raise ValueError("Native target contains a symlink")
            mode = source.stat().st_mode
            if not stat.S_ISREG(mode):
                raise ValueError("Native target is not a regular file")
            content_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            key = digest(
                [
                    self.config_hash,
                    self.rules_hash,
                    path,
                    stat.S_IMODE(mode),
                    content_hash,
                    assignments,
                ]
            )
            disposition = "reused" if self.baseline.get(path) == key else "completed"
            if disposition == "completed":
                dispatched.add(path)
            self.units.append(
                {
                    "path": path,
                    "key": key,
                    "assignments": assignments,
                    "disposition": disposition,
                }
            )
        self.expected = Counter(
            self.relative_path(task["path"])
            for task in tasks
            if self.relative_path(task["path"]) in dispatched
        )
        return dispatched

    def warning_paths(self, errors: object) -> Optional[set[str]]:
        if not isinstance(errors, list):
            return None
        paths: set[str] = set()
        for error in errors:
            if not isinstance(error, dict) or error.get("level") != "warn":
                return None
            spans = error.get("spans", [])
            if not isinstance(spans, list) or any(
                not isinstance(span, dict) for span in spans
            ):
                return None
            try:
                affected = {self.relative_path(error.get("path"))}
                affected.update(self.relative_path(span.get("file")) for span in spans)
            except ValueError:
                return None
            # Agentic Rule (ARNIE_INPUT_PARAMETER_VALIDATION): Only freshly dispatched source paths can own accepted diagnostics.
            if any(path not in self.expected for path in affected):
                return None
            paths.update(affected)
        return paths

    def complete_core(
        self,
        scanned: list[str],
        errors: list,
        skipped_rules: list,
        skipped_targets: list,
    ) -> None:
        if self.reason is not None:
            return
        warning_paths = self.warning_paths(errors)
        self.core_complete = (
            warning_paths is not None
            and not skipped_rules
            and not skipped_targets
            and Counter(self.relative_path(path) for path in scanned) == self.expected
        )
        if warning_paths is not None:
            self.core_warning_paths = warning_paths

    def seal(self, final_errors: list) -> None:
        if self.reason is None and (not self.prepared or not self.core_complete):
            return
        final_warning_paths = self.warning_paths(final_errors)
        if final_warning_paths is None:
            return
        report = self.report_path.read_bytes()
        document = object_value(json.loads(report))
        report_warning_paths = self.warning_paths(document.get("errors"))
        if report_warning_paths is None or not (
            self.core_warning_paths | final_warning_paths
        ).issubset(report_warning_paths):
            return
        manifest = {
            "schemaVersion": 1,
            "configHash": self.config_hash,
            "mode": "full" if self.reason else "incremental",
            "units": [] if self.reason else self.units,
            "reportSha256": hashlib.sha256(report).hexdigest(),
        }
        if self.reason:
            manifest["fallbackReason"] = self.reason
        # Agentic Rule (ARNIE_PATH_FILENAME_SANITIZATION): Create an exclusive temporary file before publishing the manifest.
        temporary_file = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.output_path.parent,
            prefix=".arnica-manifest-",
            suffix=".tmp",
            delete=False,
        )
        temporary = Path(temporary_file.name)
        try:
            with temporary_file:
                temporary_file.write(
                    json.dumps(manifest, sort_keys=True, separators=(",", ":"))
                )
            os.replace(temporary, self.output_path)
        finally:
            temporary.unlink(missing_ok=True)


active_scan: Optional[IncrementalScan] = None


def reset() -> None:
    global active_scan
    active_scan = None
