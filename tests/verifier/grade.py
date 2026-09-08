#!/usr/bin/env python3
"""ORDF-247 grading harness.

This is the oracle. It does not trust anything in the submitted workspace
that isn't application code: it copies the submission to a scratch
directory, stamps a pristine copy of the visible regression test file and
the hidden verifier suite on top of whatever's there (so deleting, editing,
or weakening either one has no effect), installs dependencies strictly from
the copy it just made, and runs pytest against both files with a hard
timeout. Score is computed from JUnit XML, not from grepping stdout.

Usage:
    python3 grade.py /path/to/submission/repo [--out result.json]

Exit code is 0 if the submission is a full pass, 1 otherwise -- so this can
be dropped straight into a CI step if you want a boolean gate instead of the
JSON detail.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRISTINE_HIDDEN_TEST = HERE / "test_hidden_pricing.py"
PRISTINE_VISIBLE_TEST = HERE / "fixtures" / "test_pricing.py"

TEST_TIMEOUT_SECONDS = 45
INSTALL_TIMEOUT_SECONDS = 120


def run(cmd, cwd, timeout):
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            text=True,
        )
        return proc.returncode, proc.stdout
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or "") + f"\n[grade.py] TIMED OUT after {timeout}s\n"


def parse_junit(xml_path):
    """Return {testcase_name: 'passed'|'failed'|'error'|'skipped'}."""
    results = {}
    if not xml_path.exists():
        return results
    tree = ET.parse(xml_path)
    for tc in tree.getroot().iter("testcase"):
        name = f"{tc.attrib.get('classname', '')}::{tc.attrib.get('name', '')}"
        if tc.find("failure") is not None:
            results[name] = "failed"
        elif tc.find("error") is not None:
            results[name] = "error"
        elif tc.find("skipped") is not None:
            results[name] = "skipped"
        else:
            results[name] = "passed"
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("submission", help="path to the submitted repo (post-agent workspace)")
    parser.add_argument("--out", default="result.json")
    parser.add_argument("--keep-scratch", action="store_true", help="don't delete the scratch dir (debugging)")
    args = parser.parse_args()

    submission = Path(args.submission).resolve()
    if not submission.is_dir():
        print(f"[grade.py] submission path does not exist: {submission}", file=sys.stderr)
        return 1

    scratch = Path(tempfile.mkdtemp(prefix="ordf247-grade-"))
    result = {
        "submission": str(submission),
        "scratch_dir": str(scratch),
        "steps": {},
        "regression": {},
        "hidden": {},
        "verdict": "FAIL",
        "score": 0.0,
    }

    try:
        # 1. Copy the submission verbatim -- we grade what's actually there,
        #    warts and all, we just don't let it touch the oracle itself.
        repo_copy = scratch / "repo"
        shutil.copytree(submission, repo_copy)

        # 2. Stamp the pristine test files over whatever the agent left.
        #    This is the actual anti-tampering mechanism, not a policy on
        #    paper -- see analysis/grader_attacks.md, attack #1.
        (repo_copy / "tests").mkdir(exist_ok=True)
        shutil.copyfile(PRISTINE_VISIBLE_TEST, repo_copy / "tests" / "test_pricing.py")
        verifier_dir = repo_copy / "tests" / "verifier"
        verifier_dir.mkdir(exist_ok=True)
        shutil.copyfile(PRISTINE_HIDDEN_TEST, verifier_dir / "test_hidden_pricing.py")

        # 3. Install the package itself from the copy (so a submission that
        #    edited pyproject.toml or added a genuine runtime dependency is
        #    still graded fairly).
        rc, out = run(
            [sys.executable, "-m", "pip", "install", "--quiet", "-e", "."],
            cwd=repo_copy,
            timeout=INSTALL_TIMEOUT_SECONDS,
        )
        result["steps"]["pip_install_package"] = {"returncode": rc, "output": out[-4000:]}
        if rc != 0:
            result["verdict"] = "FAIL"
            result["reason"] = "package itself failed to install"
            return 1

        # 4. Install dev/test dependencies FROM THE SUBMISSION'S OWN
        #    requirements-dev.txt. Fixing the broken pin is part of the
        #    task; if it's still broken, that's a genuine failure, not a
        #    harness bug, and we report it as such rather than crashing.
        dev_reqs = repo_copy / "requirements-dev.txt"
        if not dev_reqs.exists():
            result["verdict"] = "FAIL"
            result["reason"] = "requirements-dev.txt is missing"
            return 1
        rc, out = run(
            [sys.executable, "-m", "pip", "install", "--quiet", "-r", "requirements-dev.txt"],
            cwd=repo_copy,
            timeout=INSTALL_TIMEOUT_SECONDS,
        )
        result["steps"]["pip_install_dev"] = {"returncode": rc, "output": out[-4000:]}
        if rc != 0:
            result["verdict"] = "FAIL"
            result["reason"] = "requirements-dev.txt still does not install (pin not fixed, or broken differently)"
            return 1

        # 5. Run the regression suite and the hidden suite as two separate
        #    pytest invocations, each with its own JUnit report, each with a
        #    wall-clock timeout so a submission that hangs doesn't hang
        #    grading.
        regression_xml = scratch / "regression.xml"
        rc, out = run(
            [sys.executable, "-m", "pytest", "-q", "tests/test_pricing.py",
             f"--junitxml={regression_xml}"],
            cwd=repo_copy,
            timeout=TEST_TIMEOUT_SECONDS,
        )
        result["steps"]["pytest_regression"] = {"returncode": rc, "output": out[-6000:]}
        regression_results = parse_junit(regression_xml)
        result["regression"] = regression_results

        hidden_xml = scratch / "hidden.xml"
        rc, out = run(
            [sys.executable, "-m", "pytest", "-q", "tests/verifier/test_hidden_pricing.py",
             f"--junitxml={hidden_xml}"],
            cwd=repo_copy,
            timeout=TEST_TIMEOUT_SECONDS,
        )
        result["steps"]["pytest_hidden"] = {"returncode": rc, "output": out[-6000:]}
        hidden_results = parse_junit(hidden_xml)
        result["hidden"] = hidden_results

        # 6. Score. Hidden-suite pass rate is reported for partial-credit
        #    analysis, but the pass/fail verdict used for pass@k is strict:
        #    every regression test AND every hidden test must be green.
        # An empty result set (e.g. pytest itself errored before collecting
        # any tests) must count as a failure, not as a vacuous 1.0.
        total_hidden = len(hidden_results)
        passed_hidden = sum(1 for v in hidden_results.values() if v == "passed")
        result["score"] = (passed_hidden / total_hidden) if total_hidden else 0.0

        regression_all_pass = bool(regression_results) and all(
            v == "passed" for v in regression_results.values()
        )
        hidden_all_pass = bool(hidden_results) and all(
            v == "passed" for v in hidden_results.values()
        )

        if regression_all_pass and hidden_all_pass:
            result["verdict"] = "PASS"
            result["score"] = 1.0
        else:
            result["verdict"] = "FAIL"

        return 0 if result["verdict"] == "PASS" else 1

    finally:
        with open(args.out, "w") as f:
            json.dump(result, f, indent=2)
        print(json.dumps({k: v for k, v in result.items() if k not in ("steps",)}, indent=2))
        if not args.keep_scratch:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
