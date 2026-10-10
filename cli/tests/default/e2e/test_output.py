import collections
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict
from xml.etree import cElementTree

import pytest
from tests.conftest import mask_variable_text
from tests.conftest import RULES_PATH
from tests.conftest import TARGETS_PATH
from tests.fixtures import RunSemgrep
from tests.semgrep_runner import USE_OSEMGREP

from semgrep.constants import OutputFormat

# coupling: also in test_ci.py
REPO_DIR_NAME = "project_name"


# https://stackoverflow.com/a/10077069
@pytest.mark.kinda_slow
def _etree_to_dict(t):
    """
    A simple and sufficient XML -> dict conversion function. This function is
    used to perform basic XML test data comparisons.
    """
    d: Dict[str, Dict] = {t.tag: {}}
    children = list(t)
    if children:
        dd = collections.defaultdict(list)
        for dc in map(_etree_to_dict, children):
            for k, v in dc.items():
                dd[k].append(v)
        d = {t.tag: {k: v[0] if len(v) == 1 else v for k, v in dd.items()}}
    if t.attrib:
        d[t.tag].update(("@" + k, v) for k, v in t.attrib.items())
    if t.text:
        text = t.text.strip()
        if children or t.attrib:
            if text:
                d[t.tag]["#text"] = text
        else:
            d[t.tag] = text
    return d


@pytest.mark.kinda_slow
def test_output_highlighting(run_semgrep_in_tmp: RunSemgrep, snapshot):
    results, _errors = run_semgrep_in_tmp(
        "rules/basic.yaml",
        target_name="basic.py",
        output_format=OutputFormat.TEXT,
        strict=False,
        force_color=True,
    )
    snapshot.assert_match(
        results,
        "results.txt",
    )


@pytest.mark.kinda_slow
def test_output_highlighting__no_color(run_semgrep_in_tmp: RunSemgrep, snapshot):
    results, _errors = run_semgrep_in_tmp(
        "rules/basic.yaml",
        target_name="basic.py",
        output_format=OutputFormat.TEXT,
        strict=False,
        env={"NO_COLOR": "1"},
    )
    snapshot.assert_match(
        results,
        "results.txt",
    )


@pytest.mark.kinda_slow
def test_output_highlighting__force_color_and_no_color(
    run_semgrep_in_tmp: RunSemgrep, snapshot
):
    """
    NO_COLOR would normally disable color: https://no-color.org/

    But a tool specific flag should override a global flag.
    So when both are set, we should have color.
    """
    results, _errors = run_semgrep_in_tmp(
        "rules/basic.yaml",
        target_name="basic.py",
        output_format=OutputFormat.TEXT,
        strict=False,
        force_color=True,
        env={"NO_COLOR": "1"},
    )
    snapshot.assert_match(
        results,
        "results.txt",
    )


@pytest.mark.kinda_slow
def test_yaml_capturing(run_semgrep_in_tmp: RunSemgrep, snapshot):
    results, _errors = run_semgrep_in_tmp(
        "rules/yaml_capture.yaml",
        target_name="yaml/yaml_capture.yaml",
        output_format=OutputFormat.TEXT,
        strict=False,
    )
    snapshot.assert_match(
        results,
        "results.txt",
    )


# This test is just for making sure that our YAML parser interacts properly
# with metavariables. We don't want to introduce regressions which might
# mess this up.
@pytest.mark.kinda_slow
@pytest.mark.osemfail
def test_yaml_metavariables(run_semgrep_in_tmp: RunSemgrep, snapshot):
    stdout, _ = run_semgrep_in_tmp(
        "rules/yaml_key.yaml",
        target_name="yaml/target.yaml",
        output_format=OutputFormat.JSON,
    )
    parsed_output = json.loads(stdout)
    assert "results" in parsed_output

    for result in parsed_output["results"]:
        value = result["extra"]["metavars"]["$VALUE"]
        content = value["abstract_content"]

        # The message is newline-terminated, probably because
        # of how we parse the "message" field in the rule.
        assert content + "\n" == result["extra"]["message"]

        # The metavariable content should be faithful to the actual
        # given offset information.
        assert len(content) == value["end"]["offset"] - value["start"]["offset"]

    snapshot.assert_match(stdout, "report.json")


@pytest.mark.kinda_slow
def test_quiet_mode_has_empty_stderr(run_semgrep_in_tmp: RunSemgrep, snapshot):
    """
    Test that quiet mode doesn't print anything to stderr.

    This is because some contexts e.g. Kubernetes jobs force-mix stdout and stderr,
    and --quiet is the only way to get valid JSON output in that case.
    """
    stdout, stderr = run_semgrep_in_tmp(
        "rules/yaml_key.yaml",
        target_name="yaml/target.yaml",
        output_format=OutputFormat.JSON,
        options=["--quiet"],
    )
    assert stderr == ""
    json.loads(stdout)  # stdout must be parseable JSON


# junit-xml is tested in a test_junit_xml_output due to ambiguous XML attribute ordering
@pytest.mark.kinda_slow
@pytest.mark.parametrize(
    "format",
    ["--json", "--emacs", "--vim", "--sarif", "--gitlab-sast", "--gitlab-secrets"],
)
def test_output_format(run_semgrep_in_tmp: RunSemgrep, snapshot, format):
    stdout, _ = run_semgrep_in_tmp(
        "rules/eqeq.yaml",
        target_name="basic/stupid.py",
        options=[format],
        output_format=OutputFormat.TEXT,  # Not the real output format; just disables JSON parsing
    )
    snapshot.assert_match(stdout, "results.out")


@pytest.mark.kinda_slow
@pytest.mark.osemfail
def test_additional_outputs(run_semgrep_in_tmp: RunSemgrep, snapshot):
    stdout, _ = run_semgrep_in_tmp(
        "rules/eqeq.yaml",
        target_name="basic/stupid.py",
        options=[
            "--json-output=one.json",
            "--json-output=two.json",
            "--emacs-output=emacs.txt",
            "--vim-output=vim.txt",
            "--sarif-output=sarif.json",
            "--gitlab-sast-output=gitlab_sast.json",
            "--gitlab-secrets-output=gitlab_secrets.json",
        ],
        output_format=OutputFormat.TEXT,
    )

    snapshot.assert_match(stdout, "text.expected")
    with open("one.json") as one_json:
        snapshot.assert_match(mask_variable_text(one_json.read()), "one.json.expected")
    with open("two.json") as two_json:
        snapshot.assert_match(mask_variable_text(two_json.read()), "two.json.expected")
    with open("emacs.txt") as emacs_txt:
        snapshot.assert_match(
            mask_variable_text(emacs_txt.read()), "emacs.txt.expected"
        )
    with open("vim.txt") as vim_txt:
        snapshot.assert_match(mask_variable_text(vim_txt.read()), "vim.txt.expected")
    with open("gitlab_sast.json") as gitlab_sast_json:
        snapshot.assert_match(
            mask_variable_text(gitlab_sast_json.read()), "gitlab_sast.json.expected"
        )
    with open("gitlab_secrets.json") as gitlab_secrets_json:
        snapshot.assert_match(
            mask_variable_text(gitlab_secrets_json.read()),
            "gitlab_secrets.json.expected",
        )


@pytest.mark.kinda_slow
@pytest.mark.parametrize(
    "format",
    ["--json", "--emacs", "--vim", "--sarif", "--gitlab-sast", "--gitlab-secrets"],
)
@pytest.mark.osemfail
def test_additional_outputs_with_format_flag(
    run_semgrep_in_tmp: RunSemgrep, snapshot, format
):
    stdout, _ = run_semgrep_in_tmp(
        "rules/eqeq.yaml",
        target_name="basic/stupid.py",
        options=[
            format,
            "--json-output=result.json",
        ],
        output_format=OutputFormat.TEXT,
    )

    snapshot.assert_match(stdout, "result.expected")
    with open("result.json") as result_json:
        snapshot.assert_match(
            mask_variable_text(result_json.read()), "result.json.expected"
        )


@pytest.mark.kinda_slow
@pytest.mark.parametrize(
    "format",
    ["--json", "--emacs", "--vim", "--sarif", "--gitlab-sast", "--gitlab-secrets"],
)
@pytest.mark.osemfail
def test_additional_outputs_with_format_output_flag(
    run_semgrep_in_tmp: RunSemgrep, snapshot, format
):
    stdout, _ = run_semgrep_in_tmp(
        "rules/eqeq.yaml",
        target_name="basic/stupid.py",
        options=[format, "--sarif-output=sarif.json", "--output=result.out"],
        output_format=OutputFormat.TEXT,  # disables json parsing
    )

    with open("sarif.json") as sarif_json:
        snapshot.assert_match(
            mask_variable_text(sarif_json.read()), "sarif.json.expected"
        )
    with open("result.out") as result_out:
        snapshot.assert_match(
            mask_variable_text(result_out.read()), "result.out.expected"
        )


@pytest.mark.kinda_slow
def test_long_rule_id(run_semgrep_in_tmp: RunSemgrep, snapshot):
    stdout, _ = run_semgrep_in_tmp(
        "rules/long_rule_id.yaml",
        target_name="basic.py",
        output_format=OutputFormat.TEXT,
    )
    snapshot.assert_match(stdout, "results.out")


@pytest.mark.kinda_slow
@pytest.mark.osemfail  # TODO: fix text wrapping of findings
def test_long_rule_id_long_text(run_semgrep_in_tmp: RunSemgrep, snapshot):
    stdout, _ = run_semgrep_in_tmp(
        "rules/long_rule_id.yaml",
        target_name="long_text.py",
        output_format=OutputFormat.TEXT,
    )
    snapshot.assert_match(stdout, "results.out")


# it should not report findings from rules using the "INVENTORY" severity
@pytest.mark.kinda_slow
@pytest.mark.osemfail
def test_omit_inventory(run_semgrep_in_tmp: RunSemgrep, snapshot):
    stdout, _ = run_semgrep_in_tmp(
        "rules/severity_inventory.yaml", target_name="basic.py"
    )
    snapshot.assert_match(stdout, "results.out")


# it should not report findings from rules using the "EXPERIMENT" severity
@pytest.mark.kinda_slow
def test_omit_experiment(run_semgrep_in_tmp: RunSemgrep, snapshot):
    stdout, _ = run_semgrep_in_tmp(
        "rules/severity_experiment.yaml",
        target_name="basic.py",
    )
    snapshot.assert_match(stdout, "results.out")


@pytest.mark.kinda_slow
def test_junit_xml_output(run_semgrep_in_tmp: RunSemgrep, snapshot):
    output, _ = run_semgrep_in_tmp(
        "rules/eqeq.yaml", output_format=OutputFormat.JUNIT_XML
    )
    result = _etree_to_dict(cElementTree.XML(output))

    filename = snapshot.snapshot_dir / "results.xml"
    expected = _etree_to_dict(cElementTree.XML(filename.read_text()))

    assert result == expected


@pytest.mark.kinda_slow
@pytest.mark.osemfail
def test_junit_xml_output_flag(
    run_semgrep_in_tmp: RunSemgrep,
    snapshot,
):
    stdout, _ = run_semgrep_in_tmp(
        "rules/eqeq.yaml",
        target_name="basic/stupid.py",
        options=["--junit-xml-output=result.xml"],
        output_format=OutputFormat.TEXT,  # disables json parsing
    )

    with open("result.xml") as xml:
        snapshot.assert_match(mask_variable_text(xml.read()), "expected.xml")


@pytest.mark.kinda_slow
def test_json_output_with_dataflow_traces(run_semgrep_in_tmp: RunSemgrep, snapshot):
    snapshot.assert_match(
        run_semgrep_in_tmp(
            "rules/taint_trace.yaml",
            target_name="taint/taint_trace.cpp",
            output_format=OutputFormat.JSON,
            options=["--dataflow-traces"],
        ).stdout,
        "results.json",
    )


IGNORE_LOG_REPORT_FIRST_LINE = "Some files were skipped or only partially analyzed."
IGNORE_LOG_REPORT_LAST_LINE = (
    "  For a full list of skipped files, run opengrep with the --verbose flag.\n"
)


# pysemgrep/osemgrep status: osemgrep reports 2 more files that are being
# excluded. They're excluded in both implementations.
@pytest.mark.kinda_slow
@pytest.mark.pysemfail
def test_semgrepignore_ignore_log_report(
    run_semgrep_in_tmp: RunSemgrep, tmp_path, snapshot
):
    (tmp_path / ".semgrepignore").symlink_to(
        Path(TARGETS_PATH / "ignores" / ".semgrepignore").resolve()
    )
    # See remarks in test_ignores.py:
    shutil.copyfile(
        Path(TARGETS_PATH / "ignores" / ".gitignore"), tmp_path / ".gitignore"
    )

    _, stderr = run_semgrep_in_tmp(
        "rules/eqeq-basic.yaml",
        # This set of options is carefully crafted
        # to trigger one entry for most ignore reasons.
        # Note that the print order is non-deterministic,
        # so you must take care not to have two skips in a category.
        options=[
            "--include=ignore.*",
            "--include=tests",
            "--include=find.*",
            "--exclude=*.min.js",
            "--max-target-bytes=100",
            "--verbose",
        ],
        output_format=OutputFormat.TEXT,
        force_color=True,
        target_name="ignores",
    )

    report = re.search(
        f"^{IGNORE_LOG_REPORT_FIRST_LINE}$.*?^{IGNORE_LOG_REPORT_LAST_LINE}$",
        stderr,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert (
        report is not None
    ), "can't find ignore log report based on expected start and end lines"
    snapshot.assert_match(report.group(), "report.txt")


# Tolerate a different snapshot with pysemgrep than osemgrep.
@pytest.mark.kinda_slow
@pytest.mark.osemfail
def test_semgrepignore_ignore_log_report_pysemgrep(
    run_semgrep_in_tmp: RunSemgrep, tmp_path, snapshot
):
    test_semgrepignore_ignore_log_report(run_semgrep_in_tmp, tmp_path, snapshot)


# pysemgrep/osemgrep status: osemgrep reports 2 more files that are being
# excluded. They're excluded in both implementations.
@pytest.mark.kinda_slow
@pytest.mark.pysemfail
def test_semgrepignore_ignore_log_json_report(
    run_semgrep_in_tmp: RunSemgrep, tmp_path, snapshot
):
    (tmp_path / ".semgrepignore").symlink_to(
        Path(TARGETS_PATH / "ignores" / ".semgrepignore").resolve()
    )
    # See remarks in test_ignores.py:
    shutil.copyfile(
        Path(TARGETS_PATH / "ignores" / ".gitignore"), tmp_path / ".gitignore"
    )

    stdout, _ = run_semgrep_in_tmp(
        "rules/eqeq-basic.yaml",
        # This set of options is carefully crafted
        # to trigger one entry for most ignore reasons.
        # Note that the print order is non-deterministic,
        # so you must take care not to have two skips in a category.
        options=[
            "--include=ignore.*",
            "--include=tests",
            "--include=find.*",
            "--exclude=*.min.js",
            "--max-target-bytes=100",
            "--verbose",
        ],
        output_format=OutputFormat.JSON,
        target_name="ignores",
    )
    parsed_output = json.loads(stdout)
    assert "paths" in parsed_output

    snapshot.assert_match(
        json.dumps(parsed_output["paths"], indent=2, sort_keys=True), "report.json"
    )


# Tolerate a different snapshot with pysemgrep than osemgrep.
@pytest.mark.kinda_slow
@pytest.mark.osemfail
def test_semgrepignore_ignore_log_json_report_pysemgrep(
    run_semgrep_in_tmp: RunSemgrep, tmp_path, snapshot
):
    test_semgrepignore_ignore_log_json_report(run_semgrep_in_tmp, tmp_path, snapshot)


@pytest.mark.kinda_slow
@pytest.mark.parametrize(
    "git_repo",
    [True, False],
)
@pytest.mark.osemfail
def test_git_repo_output(
    run_semgrep: RunSemgrep, git_repo, tmp_path, monkeypatch, snapshot
):
    """
    Initialize a git repo at a temp directory
    """
    repo_base = tmp_path / REPO_DIR_NAME
    repo_base.mkdir(parents=True)

    monkeypatch.chdir(repo_base)

    if git_repo:
        # Initialize State
        subprocess.run(["git", "init"], check=True, capture_output=True)
        # Symlink the gitignore to the temp directory
        (repo_base / ".gitignore").symlink_to(
            Path(TARGETS_PATH / "ignores" / ".gitignore").resolve()
        )

    # Symlink rules
    (tmp_path / "rules").symlink_to(RULES_PATH.resolve())

    monkeypatch.chdir(tmp_path)
    snapshot.assert_match(
        run_semgrep(
            "rules/eqeq-basic.yaml",
            output_format=OutputFormat.TEXT,
            assume_targets_dir=False,
            target_name=repo_base,
        ).stderr,
        "results.txt",
    )


# This is currently not passing because the loc field in the explanation
# differs between pysemgrep and osemgrep because it's a location in the rule
# (not in the target), and pysemgrep passes a preprocessed rule file to
# semgrep-core hence the mistmatch.
@pytest.mark.slow
@pytest.mark.osemfail
def test_output_matching_explanations(run_semgrep_in_tmp: RunSemgrep, snapshot):
    stdout, _ = run_semgrep_in_tmp(
        "rules/eqeq-basic.yaml",
        target_name="basic/stupid.js",
        options=["--matching-explanations"],
        output_format=OutputFormat.JSON,  # Not the real output format; just disables JSON parsing
    )
    snapshot.assert_match(stdout, "report.json")


@pytest.mark.kinda_slow
@pytest.mark.parametrize(
    "target_dir",
    ["multilangproj", "language-filtering", "exclude_include"],
)
@pytest.mark.osemfail
def test_file_count_multifile(run_semgrep_in_tmp: RunSemgrep, snapshot, target_dir):
    _, stderr = run_semgrep_in_tmp(
        "rules/filecount.yaml",
        output_format=OutputFormat.TEXT,
        target_name=target_dir,
        options=[],
    )
    snapshot.assert_match(stderr, "result.out")


@pytest.mark.parametrize("extension", ["js", "ts"])
@pytest.mark.kinda_slow
def test_destructured_parameter_defaults(run_semgrep_in_tmp: RunSemgrep, extension):
    stdout, _ = run_semgrep_in_tmp(
        "rules/destructured_parameter_defaults.yaml",
        target_name=f"destructured_parameter_defaults.{extension}",
        output_format=OutputFormat.JSON,
        options=["--no-rewrite-rule-ids"],
        clean_fingerprint=False,
    )
    output = json.loads(stdout)
    assert output["errors"] == []
    actual = [
        {
            "function": result["extra"]["metavars"]["$F"]["abstract_content"],
            "capture": result["extra"]["metavars"]["$PARAM"]["abstract_content"],
            "fingerprint": result["extra"]["fingerprint"],
        }
        for result in output["results"]
    ]
    # Captured from released 1.15.0; list equality also checks occurrence counts.
    expected_name = (
        "destructured_parameter_defaults.native.json"
        if USE_OSEMGREP
        else "destructured_parameter_defaults.json"
    )
    expected = json.loads((TARGETS_PATH / expected_name).read_text())[extension]
    assert actual == expected


@pytest.mark.kinda_slow
def test_legacy_fingerprints(run_semgrep_in_tmp: RunSemgrep):
    stdout, _ = run_semgrep_in_tmp(
        "rules/legacy_fingerprints.yaml",
        target_name="legacy_fingerprints",
        strict=False,
        output_format=OutputFormat.JSON,
        options=["--no-rewrite-rule-ids"],
        clean_fingerprint=False,
    )
    output = json.loads(stdout)
    assert [(error["path"], error["type"][0]) for error in output["errors"]] == [
        ("targets/legacy_fingerprints/capture.dockerfile", "PartialParsing")
    ]
    actual = [
        {
            "rule": result["check_id"],
            "path": result["path"],
            "line": result["start"]["line"],
            "fingerprint": result["extra"]["fingerprint"],
            "captures": {
                name: value["abstract_content"]
                for name, value in result["extra"]["metavars"].items()
            },
        }
        for result in output["results"]
    ]
    # Released 1.15.0 output, including duplicate suffixes and symbolic modes.
    expected_name = "expected.native.json" if USE_OSEMGREP else "expected.json"
    expected = json.loads(
        (TARGETS_PATH / "legacy_fingerprints" / expected_name).read_text()
    )
    assert actual == expected


@pytest.mark.parametrize(
    "fixture",
    [
        "legacy_parser_fingerprints",
        "legacy_ruby_calls",
        "legacy_default_findings",
        "legacy_capture_languages",
        "legacy_symbolic_eligibility",
        "legacy_review_regressions",
        "legacy_elixir_captures",
        "legacy_elixir_taint",
        "legacy_elixir_nested",
        "legacy_elixir_review_regressions",
    ],
)
@pytest.mark.slow
def test_legacy_syntax_fingerprints(run_semgrep_in_tmp: RunSemgrep, fixture):
    stdout, _ = run_semgrep_in_tmp(
        f"rules/{fixture}.yaml",
        target_name=fixture,
        strict=False,
        output_format=OutputFormat.JSON,
        options=["--no-rewrite-rule-ids"],
        clean_fingerprint=False,
    )
    output = json.loads(stdout)
    actual = [
        {
            "rule": result["check_id"],
            "path": result["path"],
            "start": result["start"],
            "end": result["end"],
            "fingerprint": result["extra"]["fingerprint"],
            "captures": {
                name: value["abstract_content"]
                for name, value in result["extra"]["metavars"].items()
            },
        }
        for result in output["results"]
    ]
    expected_name = "expected.native.json" if USE_OSEMGREP else "expected.json"
    expected = json.loads((TARGETS_PATH / fixture / expected_name).read_text())
    if fixture == "legacy_review_regressions" or fixture.startswith("legacy_elixir_"):
        for row, result in zip(actual, output["results"]):
            row["message"] = result["extra"]["message"]
    if fixture == "legacy_parser_fingerprints":
        assert sorted(error["path"] for error in output["errors"]) == (
            expected["parse_error_paths"]
        )
        assert all(error["type"][0] == "PartialParsing" for error in output["errors"])
        expected = expected["results"]
    else:
        assert output["errors"] == []
    assert actual == expected


@pytest.mark.parametrize("reverse_rules", [False, True])
@pytest.mark.kinda_slow
def test_elixir_compatibility_preserves_security(
    run_semgrep_in_tmp: RunSemgrep, tmp_path, reverse_rules
):
    config = json.loads((RULES_PATH / "legacy_elixir_security.yaml").read_text())
    if reverse_rules:
        config["rules"].reverse()
    rule_file = tmp_path / "elixir-security.json"
    rule_file.write_text(json.dumps(config))
    stdout, _ = run_semgrep_in_tmp(
        rule_file,
        target_name="legacy_elixir_security/filters.ex",
        output_format=OutputFormat.JSON,
        options=["--no-rewrite-rule-ids"],
    )
    output = json.loads(stdout)
    assert output["errors"] == []
    assert sorted(result["check_id"] for result in output["results"]) == [
        "legacy-sanitizer",
        "legacy-text",
        "modern-text",
        "original-label-filter",
        "taint-control",
        "taint-legacy-sink",
        "taint-modern-sink",
    ]


@pytest.mark.parametrize("cli_mode", ["legacy", "experimental"])
@pytest.mark.kinda_slow
def test_elixir_nested_shared_syntax(run_semgrep_in_tmp: RunSemgrep, cli_mode):
    options = [
        f"--{cli_mode}",
        "--no-rewrite-rule-ids",
        "--max-memory",
        "512",
        "--timeout",
        "10",
        "--jobs",
        "1",
    ]
    if cli_mode == "experimental":
        options.extend(["--project-root", "."])
    stdout, _ = run_semgrep_in_tmp(
        "rules/legacy_elixir_shared.yaml",
        target_name="legacy_elixir_shared",
        output_format=OutputFormat.JSON,
        options=options,
        clean_fingerprint=False,
    )
    output = json.loads(stdout)
    assert output["errors"] == []
    actual = [
        {
            "rule": result["check_id"],
            "path": result["path"],
            "start": result["start"],
            "end": result["end"],
            "message": result["extra"]["message"],
            "metavars": result["extra"]["metavars"],
        }
        for result in output["results"]
    ]
    # Released 1.15 captures and locations; CLI fingerprint formats differ.
    expected = json.loads(
        (TARGETS_PATH / "legacy_elixir_shared/expected.json").read_text()
    )
    assert actual == expected["findings"]
    assert [result["extra"]["fingerprint"] for result in output["results"]] == (
        expected["fingerprints"][cli_mode]
    )


@pytest.mark.parametrize("cli_mode", ["legacy", "experimental"])
@pytest.mark.parametrize("error_on_findings", [False, True])
@pytest.mark.parametrize("subcommand", [None, "scan"])
@pytest.mark.kinda_slow
def test_nested_legacy_errors_preserve_findings(
    run_semgrep_in_tmp: RunSemgrep, cli_mode, error_on_findings, subcommand
):
    options = [f"--{cli_mode}", "--no-rewrite-rule-ids"]
    if cli_mode == "experimental":
        options.extend(["--project-root", "."])
    if error_on_findings:
        options.append("--error")
    stdout, _ = run_semgrep_in_tmp(
        "rules/nested_legacy_errors.yaml",
        subcommand=subcommand,
        target_name="nested_legacy_errors",
        strict=False,
        assert_exit_code=1 if error_on_findings else 0,
        options=options,
        clean_fingerprint=False,
    )
    output = json.loads(stdout)
    expected = json.loads(
        (TARGETS_PATH / "nested_legacy_errors/expected.json").read_text()
    )
    assert output["results"] == expected[cli_mode]
    errors = output["errors"]
    assert len(errors) == 4
    assert all(error["level"] == "warn" for error in errors)
    assert all(
        error["path"]
        in [
            "targets/nested_legacy_errors/bad.yaml",
            "targets/nested_legacy_errors/direct.ex",
        ]
        for error in errors
    )
    partial_errors = [error for error in errors if isinstance(error["type"], list)]
    assert len(partial_errors) == 3
    assert (
        next(
            error["type"][1][0]
            for error in partial_errors
            if error["path"].endswith("direct.ex")
        )
        == expected["direct_error_span"]
    )
    for error in partial_errors:
        kind, spans = error["type"]
        assert kind == "PartialParsing"
        assert len(spans) == 1
        assert spans[0]["path"] == error["path"]
        assert spans[0]["start"]["offset"] < spans[0]["end"]["offset"]
        assert error["spans"] == [
            {"file": span["path"], "start": span["start"], "end": span["end"]}
            for span in spans
        ]
    assert any(error["type"] == "Internal matching error" for error in errors)


@pytest.mark.parametrize("cli_mode", ["legacy", "experimental"])
@pytest.mark.kinda_slow
def test_nested_legacy_only_error_is_fatal(run_semgrep_in_tmp: RunSemgrep, cli_mode):
    options = [f"--{cli_mode}", "--no-rewrite-rule-ids"]
    if cli_mode == "experimental":
        options.extend(["--project-root", "."])
    stdout, _ = run_semgrep_in_tmp(
        "rules/nested_legacy_only_error.yaml",
        target_name="nested_legacy_only_error.yaml",
        strict=False,
        assert_exit_code=2,
        options=options,
    )
    output = json.loads(stdout)
    assert output["results"] == []
    assert len(output["errors"]) == 1
    assert output["errors"][0]["type"] == "Fatal error"
    assert "Legacy fingerprint matching failed" in output["errors"][0]["message"]


@pytest.mark.kinda_slow
def test_elixir_modern_propagators(run_semgrep_in_tmp: RunSemgrep):
    stdout, _ = run_semgrep_in_tmp(
        "rules/legacy_elixir_propagators.yaml",
        target_name="legacy_elixir_security/propagators.ex",
        output_format=OutputFormat.JSON,
        options=["--no-rewrite-rule-ids"],
    )
    output = json.loads(stdout)
    assert output["errors"] == []
    assert [
        (result["check_id"], result["extra"]["metavars"]["$X"]["abstract_content"])
        for result in output["results"]
    ] == [("modern-propagator", "User{}"), ("modern-propagator", "b")]


@pytest.mark.kinda_slow
def test_elixir_modern_struct_taint(run_semgrep_in_tmp: RunSemgrep):
    stdout, _ = run_semgrep_in_tmp(
        "rules/legacy_elixir_struct_params.yaml",
        target_name="legacy_elixir_security/struct_params.ex",
        output_format=OutputFormat.JSON,
    )
    output = json.loads(stdout)
    assert output["errors"] == []
    assert [result["start"]["line"] for result in output["results"]] == [
        6,
        12,
        18,
        23,
        29,
        34,
        40,
    ]


@pytest.mark.kinda_slow
def test_elixir_pipeline_analysis(run_semgrep_in_tmp: RunSemgrep):
    stdout, _ = run_semgrep_in_tmp(
        "rules/legacy_elixir_pipeline_security.yaml",
        target_name="legacy_elixir_review_regressions/pipelines.ex",
        output_format=OutputFormat.JSON,
        options=["--no-rewrite-rule-ids"],
    )
    output = json.loads(stdout)
    assert output["errors"] == []
    assert [(r["check_id"], r["start"]["line"]) for r in output["results"]] == [
        ("direct-call", 8),
        ("direct-call", 14),
        ("pipeline-taint", 17),
    ]


@pytest.mark.parametrize("legacy_cli", [False, True])
@pytest.mark.parametrize("warning_name", [None, "a-warning.ex", "z-warning.ex"])
@pytest.mark.parametrize("error_on_findings", [False, True])
@pytest.mark.parametrize("with_finding", [False, True])
@pytest.mark.slow
def test_legacy_propagation_failure_is_fatal(
    run_semgrep_in_tmp: RunSemgrep,
    tmp_path,
    legacy_cli,
    warning_name,
    error_on_findings,
    with_finding,
):
    targets = tmp_path / "compatibility-targets"
    targets.mkdir()
    (targets / "limit.ex").write_text(
        "defmodule Large do\ndef f() do\n"
        + "n()\n" * 100010
        + 'sink("unsafe")\nend\nend\n'
    )
    if with_finding:
        (targets / "control.ex").write_text('sink("unsafe")\n')
    if warning_name:
        (targets / warning_name).write_text(")\n# sink\n")
    rules = tmp_path / "compatibility-rules.json"
    rules.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "id": "sink",
                        "languages": ["elixir"],
                        "pattern": "sink(...)",
                        "message": "Sink",
                        "severity": "WARNING",
                    }
                ]
            }
        )
    )
    options = [
        "--jobs",
        "1",
        "--timeout",
        "0",
        "--legacy" if legacy_cli else "--experimental",
    ]
    if error_on_findings:
        options.append("--error")
    stdout, _ = run_semgrep_in_tmp(
        rules,
        target_name=targets.name,
        assume_targets_dir=False,
        strict=False,
        assert_exit_code=2,
        output_format=OutputFormat.JSON,
        options=options,
    )
    output = json.loads(stdout)
    assert [Path(r["path"]).name for r in output["results"]] == (
        ["control.ex"] if with_finding else []
    )
    fatal = [error for error in output["errors"] if error["level"] == "error"]
    assert len(fatal) == 1
    assert fatal[0]["type"] == "Fatal error"
    assert Path(fatal[0]["path"]).name == "limit.ex"
    if warning_name:
        assert any(
            error["level"] == "warn" and Path(error["path"]).name == warning_name
            for error in output["errors"]
        )


@pytest.mark.kinda_slow
def test_legacy_kotlin_large_capture_fingerprint(run_semgrep_in_tmp: RunSemgrep):
    stdout, _ = run_semgrep_in_tmp(
        "rules/legacy_fingerprints.yaml",
        target_name="legacy_kotlin_large_capture.kt",
        output_format=OutputFormat.JSON,
        options=["--no-rewrite-rule-ids"],
        clean_fingerprint=False,
    )
    output = json.loads(stdout)
    assert output["errors"] == []
    assert len(output["results"]) == 1
    result = output["results"][0]
    assert result["extra"]["fingerprint"] == (
        "b764b0fb63237071f9176ab3c878dc247f8e42c4e886c666303a3798ec99ebbbb011"
        "cff287f25b28314b1a17153b298dfadf350df8a6e38b2319cba6834b7fd6_0"
    )
    assert len(result["extra"]["metavars"]["$X"]["abstract_content"]) == 343988


@pytest.mark.slow
def test_legacy_kotlin_reporting_is_bounded(run_semgrep_in_tmp: RunSemgrep):
    stdout, stderr = run_semgrep_in_tmp(
        "rules/legacy_fingerprints.yaml",
        target_name="legacy_kotlin_chain.kt",
        output_format=OutputFormat.JSON,
        options=["--no-rewrite-rule-ids"],
        strict=False,
        assert_exit_code=2,
    )
    message = "Legacy fingerprint capture exceeds 20,000,000 token visits"
    if USE_OSEMGREP:
        assert stdout == ""
        assert message in stderr
    else:
        output = json.loads(stdout)
        assert output["results"] == []
        assert len(output["errors"]) == 1
        assert message in output["errors"][0]["message"]


@pytest.mark.slow
def test_rule_stack_overflow_preserves_other_findings(run_semgrep_in_tmp: RunSemgrep):
    stdout, _ = run_semgrep_in_tmp(
        "rules/stack_overflow.yaml",
        target_name="stack_overflow.c",
        output_format=OutputFormat.JSON,
        options=["--no-rewrite-rule-ids", "--timeout", "30"],
        strict=False,
    )
    output = json.loads(stdout)
    assert [(r["check_id"], r["start"]["line"]) for r in output["results"]] == [
        ("string-copy", 9)
    ]
    assert sorted((e["type"], e["rule_id"]) for e in output["errors"]) == [
        ("Stack overflow", "recursive-capture"),
        ("Stack overflow", "recursive-taint-capture"),
    ]


@pytest.mark.kinda_slow
def test_csharp_indexer_alias_matching(run_semgrep_in_tmp: RunSemgrep):
    stdout, _ = run_semgrep_in_tmp(
        "rules/csharp_modern_indexer.yaml",
        target_name="legacy_review_regressions/aliases.cs",
        output_format=OutputFormat.JSON,
    )
    output = json.loads(stdout)
    assert output["errors"] == []
    assert [result["start"]["line"] for result in output["results"]] == [4, 5, 6]


@pytest.mark.kinda_slow
def test_nested_legacy_capture_locations(run_semgrep_in_tmp: RunSemgrep):
    stdout, _ = run_semgrep_in_tmp(
        "rules/nested_legacy_provenance.yaml",
        target_name="nested_legacy_provenance.py",
        output_format=OutputFormat.JSON,
        options=["--no-rewrite-rule-ids"],
    )
    output = json.loads(stdout)
    assert output["errors"] == []
    assert sorted(
        (result["check_id"], result["extra"]["message"]) for result in output["results"]
    ) == sorted(
        (rule, f"Capture sink(a) {capture}")
        for rule in ["double", "single"]
        for capture in ["$INNER", "a", "wrap(source())"]
    )
    source = (TARGETS_PATH / "nested_legacy_provenance.py").read_bytes()
    for result in output["results"]:
        for capture in result["extra"]["metavars"].values():
            start = capture["start"]["offset"]
            end = capture["end"]["offset"]
            assert source[start:end].decode() == capture["abstract_content"]


@pytest.mark.kinda_slow
def test_symbolic_propagation_keeps_modern_matches(run_semgrep_in_tmp: RunSemgrep):
    stdout, _ = run_semgrep_in_tmp(
        "rules/symbolic_modern_matches.yaml",
        target_name="symbolic_modern_matches.py",
        output_format=OutputFormat.JSON,
        options=["--no-rewrite-rule-ids"],
    )
    output = json.loads(stdout)
    assert output["errors"] == []
    actual = [
        (
            result["check_id"],
            result["start"]["line"],
            {
                name: value["abstract_content"]
                for name, value in result["extra"]["metavars"].items()
            },
        )
        for result in output["results"]
    ]
    expected = [
        ("nested", 2, {"$X": "x"}),
        ("nested", 2, {"$X": "x", "$Y": "[a]"}),
        ("regex", 2, {"$X": "x"}),
        ("nested", 8, {"$X": "make(a)"}),
        ("nested", 8, {"$X": "make(a)", "$Y": "a"}),
        ("regex", 8, {"$X": "make(a)"}),
    ]
    assert collections.Counter(json.dumps(row, sort_keys=True) for row in actual) == (
        collections.Counter(json.dumps(row, sort_keys=True) for row in expected)
    )
