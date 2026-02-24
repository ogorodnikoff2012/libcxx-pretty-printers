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

import argparse
import glob
import os
import re
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DOCKERFILE = os.path.join(SCRIPT_DIR, "Dockerfile")
IMAGE_PREFIX = "libcxx-pp-test"

DEFAULT_LLVM_VERSIONS = ["18", "21"]
COMPILE_FLAGS = "-stdlib=libc++ -g -O0 -std=c++17 -fno-limit-debug-info"
DOCKER_TIMEOUT = 120


# -- Docker image management ---------------------------------------------------

def image_exists(tag):
    """Check if a Docker image exists locally."""
    result = subprocess.run(
        ["docker", "image", "inspect", tag],
        capture_output=True, timeout=10,
    )
    return result.returncode == 0


def build_image(llvm_version, quiet=True):
    """Build a Docker image for the given LLVM version."""
    tag = f"{IMAGE_PREFIX}:{llvm_version}"
    cmd = [
        "docker", "build",
        "--build-arg", f"LLVM_VERSION={llvm_version}",
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


def ensure_images(versions, rebuild=False, verbose=False):
    """Ensure Docker images exist for all requested versions. Returns available versions."""
    available = []
    for ver in versions:
        tag = f"{IMAGE_PREFIX}:{ver}"
        if not rebuild and image_exists(tag):
            available.append(ver)
            continue
        action = "Rebuilding" if rebuild else "Building"
        print(f"  {action} {tag}...")
        ok, msg = build_image(ver, quiet=not verbose)
        if ok:
            available.append(ver)
        else:
            print(f"  SKIP clang-{ver}: {msg}")
    return available


# -- Test discovery ------------------------------------------------------------

def discover_tests(test_filter=None):
    """Find test cases under tests/. Each is a directory with test_*.cpp."""
    cases = []
    for cpp in sorted(glob.glob(os.path.join(SCRIPT_DIR, "*/test_*.cpp"))):
        test_dir = os.path.dirname(cpp)
        test_name = os.path.basename(test_dir)
        if test_filter and test_name != test_filter:
            continue
        base = os.path.splitext(os.path.basename(cpp))[0]
        gdb_script = os.path.join(test_dir, base + ".gdb")
        expected = os.path.join(test_dir, "expected.txt")
        if not os.path.exists(gdb_script):
            print(f"  SKIP {test_name}: missing {base}.gdb")
            continue
        cases.append({
            "name": test_name,
            "cpp": cpp,
            "gdb_script": gdb_script,
            "expected": expected,
            "dir": test_dir,
            # Paths relative to tests/ for use inside the container
            "container_cpp": f"/workspace/tests/{test_name}/{base}.cpp",
            "container_gdb": f"/workspace/tests/{test_name}/{base}.gdb",
        })
    return cases


# -- Docker execution ----------------------------------------------------------

def run_docker_test(llvm_version, test, verbose=False):
    """Run a test inside a Docker container. Returns (ok, result).

    On success result is a list of parsed output lines.
    On failure result is an error message string.
    """
    tag = f"{IMAGE_PREFIX}:{llvm_version}"
    compiler = f"clang++-{llvm_version}"

    # Build the shell command that runs inside the container
    inner_script = (
        f"cd /tmp && "
        f"{compiler} {COMPILE_FLAGS} -o test_binary {test['container_cpp']} && "
        f"PRINTER_PATH=/workspace/src "
        f"gdb --batch --quiet -nh -x {test['container_gdb']} ./test_binary"
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
        print(f"--- docker stdout (clang++-{llvm_version} / {test['name']}) ---")
        print(stdout)
        if stderr:
            print(f"--- docker stderr ---")
            print(stderr)
        print("--- end ---")

    # Parse tagged output
    actual = parse_output(stdout)
    if not actual:
        return False, (
            f"no @@@ output captured\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}"
        )

    return True, actual


# -- Output parsing ------------------------------------------------------------

def parse_output(raw):
    """Extract @@@ tagged lines from GDB output, strip prefix."""
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("@@@ "):
            lines.append(line[4:])
    return lines


# -- Comparison ----------------------------------------------------------------

def line_matches(actual, expected):
    """Check if actual line matches expected, supporting capacity=* wildcard."""
    pattern = re.escape(expected).replace(r"capacity=\*", r"capacity=\d+")
    return re.fullmatch(pattern, actual) is not None


def compare_output(actual_lines, expected_lines):
    """Compare actual vs expected. Returns list of (lineno, actual, expected)."""
    errors = []
    max_lines = max(len(actual_lines), len(expected_lines))
    for i in range(max_lines):
        act = actual_lines[i].strip() if i < len(actual_lines) else "<missing>"
        exp = expected_lines[i].strip() if i < len(expected_lines) else "<missing>"
        if not line_matches(act, exp):
            errors.append((i + 1, act, exp))
    return errors


# -- CLI helpers ---------------------------------------------------------------

def parse_llvm_version(compiler_arg):
    """Extract LLVM version number from --compiler arg like 'clang++-18' or '18'."""
    m = re.search(r"(\d+)", compiler_arg)
    if m:
        return m.group(1)
    return compiler_arg


# -- Main ----------------------------------------------------------------------

def main():
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
    print(f"  Found: {', '.join(t['name'] for t in tests)}")

    passed = 0
    failed = 0

    for test in tests:
        for ver in available:
            label = f"{test['name']} / clang++-{ver}"
            ok, result = run_docker_test(ver, test, args.verbose)

            if not ok:
                print(f"  FAIL  {label}: {result}")
                failed += 1
                continue

            actual_lines = result

            # --update mode: write expected.txt from actual output
            if args.update:
                with open(test["expected"], "w") as f:
                    f.write("\n".join(actual_lines) + "\n")
                print(f"  UPDATED  {label} -> {test['expected']}")
                passed += 1
                continue

            # Compare with expected
            if not os.path.exists(test["expected"]):
                print(f"  FAIL  {label}: expected.txt not found (run with --update to create)")
                failed += 1
                continue

            with open(test["expected"]) as f:
                expected_lines = [l.strip() for l in f.readlines() if l.strip()]

            errors = compare_output(actual_lines, expected_lines)
            if errors:
                print(f"  FAIL  {label}:")
                for lineno, act, exp in errors:
                    print(f"    line {lineno}:")
                    print(f"      expected: {exp}")
                    print(f"      actual:   {act}")
                failed += 1
            else:
                print(f"  PASS  {label}")
                passed += 1

    print()
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
