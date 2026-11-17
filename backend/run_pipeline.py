import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run backend tests, then the live 10-row LLM smoke test."
    )
    parser.add_argument(
        "--tests-only",
        action="store_true",
        help="Skip the live LLM smoke test.",
    )
    arguments = parser.parse_args()
    backend_dir = Path(__file__).resolve().parent

    print("Running backend tests...", flush=True)
    test_result = subprocess.call(
        [sys.executable, "run_tests.py"],
        cwd=backend_dir,
    )
    if test_result != 0 or arguments.tests_only:
        return test_result

    print("Running live LLM pipeline smoke test...", flush=True)
    return subprocess.call(
        [sys.executable, "run_pipeline_smoke_test.py"],
        cwd=backend_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
