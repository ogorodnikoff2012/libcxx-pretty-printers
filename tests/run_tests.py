#!/usr/bin/env python3
"""Test runner for libc++ GDB pretty-printers.

Builds Docker containers with specific clang/libc++ versions, compiles C++ test
files inside them, runs under GDB with pretty-printers loaded, and compares
output against expected results.

Usage:
    python3 tests/run_tests.py                          # run all tests, both containers
    python3 tests/run_tests.py --compiler clang++-18    # specific version only
    python3 tests/run_tests.py --test vector            # specific test case
    python3 tests/run_tests.py --update                 # regenerate expected.txt
    python3 tests/run_tests.py --verbose                # show full GDB output
    python3 tests/run_tests.py --rebuild                # force rebuild Docker images
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DOCKERFILE = os.path.join(SCRIPT_DIR, "Dockerfile")
IMAGE_PREFIX = "libcxx-pp-test"

DEFAULT_LLVM_VERSIONS = ["18", "21"]
COMPILE_FLAGS = "-stdlib=libc++ -g -O0 -std=c++17 -fno-limit-debug-info"
DOCKER_TIMEOUT = 120


# -- Data types ----------------------------------------------------------------

@dataclass
class TestCase:
    name: str
    cpp: str
    gdb_script: str
    expected: str
    container_cpp: str
    container_gdb: str


@dataclass
class Mismatch:
    line: int
    actual: str
    expected: str


# -- Docker image management ---------------------------------------------------

DOCKERFILE_HASH_LABEL = "dockerfile.hash"


def dockerfile_hash() -> str:
    """Compute sha256 of the Dockerfile."""
    with open(DOCKERFILE, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def image_needs_rebuild(tag: str) -> bool:
    """Check if an image is missing or was built from a stale Dockerfile."""
    result = subprocess.run(
        ["docker", "image", "inspect", tag],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        return True
    try:
        info = json.loads(result.stdout)
        stored = info[0].get("Config", {}).get("Labels", {}).get(DOCKERFILE_HASH_LABEL)
        return stored != dockerfile_hash()
    except (json.JSONDecodeError, IndexError, KeyError):
        return True


def build_image(llvm_version: str, quiet: bool = True) -> tuple[bool, str]:
    """Build a Docker image for the given LLVM version."""
    tag = f"{IMAGE_PREFIX}:{llvm_version}"
    cmd = [
        "docker", "build",
        "--build-arg", f"LLVM_VERSION={llvm_version}",
        "--label", f"{DOCKERFILE_HASH_LABEL}={dockerfile_hash()}",
        "-t", tag,
        "-f", DOCKERFILE,
        SCRIPT_DIR,
    ]
    if quiet:
        cmd.insert(2, "--quiet")
    result = subprocess.run(cmd, capture_output=quiet, text=True, timeout=600)
    if result.returncode != 0:
        stderr = result.stderr if quiet else ""
        return False, f"docker build failed:\n{stderr}"
    return True, tag


def ensure_images(
    versions: list[str], *, rebuild: bool = False, verbose: bool = False,
) -> list[str]:
    """Ensure Docker images exist for all requested versions. Returns available versions."""
    available: list[str] = []
    for ver in versions:
        tag = f"{IMAGE_PREFIX}:{ver}"
        if not rebuild and not image_needs_rebuild(tag):
            available.append(ver)
            continue
        reason = "forced" if rebuild else "Dockerfile changed"
        print(f"  Building {tag} ({reason})...")
        ok, msg = build_image(ver, quiet=not verbose)
        if ok:
            available.append(ver)
        else:
            print(f"  SKIP clang-{ver}: {msg}")
    return available


# -- Test discovery ------------------------------------------------------------

def discover_tests(test_filter: str | None = None) -> list[TestCase]:
    """Find test cases under tests/. Each is a directory with test_*.cpp."""
    cases: list[TestCase] = []
    for cpp in sorted(glob.glob(os.path.join(SCRIPT_DIR, "*/test_*.cpp"))):
        test_dir = os.path.dirname(cpp)
        test_name = os.path.basename(test_dir)
        if test_filter and test_name != test_filter:
            continue
        base = os.path.splitext(os.path.basename(cpp))[0]
        gdb_script = os.path.join(test_dir, base + ".gdb")
        if not os.path.exists(gdb_script):
            print(f"  SKIP {test_name}: missing {base}.gdb")
            continue
        cases.append(TestCase(
            name=test_name,
            cpp=cpp,
            gdb_script=gdb_script,
            expected=os.path.join(test_dir, "expected.txt"),
            container_cpp=f"/workspace/tests/{test_name}/{base}.cpp",
            container_gdb=f"/workspace/tests/{test_name}/{base}.gdb",
        ))
    return cases


# -- Docker execution ----------------------------------------------------------

def run_docker_test(
    llvm_version: str, test: TestCase, *, verbose: bool = False,
) -> tuple[bool, list[str] | str]:
    """Run a test inside a Docker container.

    Returns (True, parsed_lines) on success or (False, error_message) on failure.
    """
    tag = f"{IMAGE_PREFIX}:{llvm_version}"
    compiler = f"clang++-{llvm_version}"

    inner_script = (
        f"cd /tmp && "
        f"{compiler} {COMPILE_FLAGS} -o test_binary {test.container_cpp} && "
        f"PRINTER_PATH=/workspace/src "
        f"gdb --batch --quiet -nh -x {test.container_gdb} ./test_binary"
    )

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{os.path.join(REPO_ROOT, 'src')}:/workspace/src:ro",
        "-v", f"{SCRIPT_DIR}:/workspace/tests:ro",
        tag,
        "bash", "-c", inner_script,
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=DOCKER_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return False, "Docker container timed out"

    stdout, stderr = result.stdout, result.stderr

    if verbose:
        print(f"--- docker stdout (clang++-{llvm_version} / {test.name}) ---")
        print(stdout)
        if stderr:
            print("--- docker stderr ---")
            print(stderr)
        print("--- end ---")

    actual = parse_output(stdout)
    if not actual:
        return False, (
            f"no @@@ output captured\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}"
        )

    return True, actual


# -- Output parsing ------------------------------------------------------------

def parse_output(raw: str) -> list[str]:
    """Extract @@@ tagged lines from GDB output, strip prefix."""
    return [
        line.strip()[4:]
        for line in raw.splitlines()
        if line.strip().startswith("@@@ ")
    ]


# -- Comparison ----------------------------------------------------------------

def line_matches(actual: str, expected: str) -> bool:
    """Check if actual line matches expected, supporting capacity=* wildcard."""
    pattern = re.escape(expected).replace(r"capacity=\*", r"capacity=\d+")
    return re.fullmatch(pattern, actual) is not None


def compare_output(actual_lines: list[str], expected_lines: list[str]) -> list[Mismatch]:
    """Compare actual vs expected. Returns list of mismatches."""
    errors: list[Mismatch] = []
    max_lines = max(len(actual_lines), len(expected_lines))
    for i in range(max_lines):
        act = actual_lines[i].strip() if i < len(actual_lines) else "<missing>"
        exp = expected_lines[i].strip() if i < len(expected_lines) else "<missing>"
        if not line_matches(act, exp):
            errors.append(Mismatch(line=i + 1, actual=act, expected=exp))
    return errors


# -- CLI helpers ---------------------------------------------------------------

def parse_llvm_version(compiler_arg: str) -> str:
    """Extract LLVM version number from --compiler arg like 'clang++-18' or '18'."""
    m = re.search(r"(\d+)", compiler_arg)
    return m.group(1) if m else compiler_arg


# -- Main ----------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test runner for libc++ GDB pretty-printers (Docker-based)",
    )
    parser.add_argument("--compiler", help="Specific compiler/version (e.g. clang++-18 or 18)")
    parser.add_argument("--test", help="Specific test case to run")
    parser.add_argument("--update", action="store_true", help="Update expected.txt from actual output")
    parser.add_argument("--verbose", action="store_true", help="Show full Docker/GDB output")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild Docker images")
    args = parser.parse_args()

    if args.compiler:
        versions = [parse_llvm_version(args.compiler)]
    else:
        versions = DEFAULT_LLVM_VERSIONS

    print("Preparing Docker images...")
    available = ensure_images(versions, rebuild=args.rebuild, verbose=args.verbose)
    if not available:
        print("ERROR: No Docker images available.")
        sys.exit(2)
    print(f"  Ready: {', '.join(f'clang++-{v}' for v in available)}")

    print("Discovering tests...")
    tests = discover_tests(args.test)
    if not tests:
        print("ERROR: No test cases found.")
        sys.exit(2)
    print(f"  Found: {', '.join(t.name for t in tests)}")

    passed = 0
    failed = 0

    for test in tests:
        for ver in available:
            label = f"{test.name} / clang++-{ver}"
            ok, result = run_docker_test(ver, test, verbose=args.verbose)

            if not ok:
                print(f"  FAIL  {label}: {result}")
                failed += 1
                continue

            actual_lines: list[str] = result  # type: ignore[assignment]

            # --update mode: write expected.txt from actual output
            if args.update:
                with open(test.expected, "w") as f:
                    f.write("\n".join(actual_lines) + "\n")
                print(f"  UPDATED  {label} -> {test.expected}")
                passed += 1
                continue

            # Compare with expected
            if not os.path.exists(test.expected):
                print(f"  FAIL  {label}: expected.txt not found (run with --update to create)")
                failed += 1
                continue

            with open(test.expected) as f:
                expected_lines = [l.strip() for l in f.readlines() if l.strip()]

            errors = compare_output(actual_lines, expected_lines)
            if errors:
                print(f"  FAIL  {label}:")
                for err in errors:
                    print(f"    line {err.line}:")
                    print(f"      expected: {err.expected}")
                    print(f"      actual:   {err.actual}")
                failed += 1
            else:
                print(f"  PASS  {label}")
                passed += 1

    print()
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
