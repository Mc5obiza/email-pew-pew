import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the backend test suite.")
    parser.add_argument(
        "--suite",
        choices=("all", "unit", "integration"),
        default="all",
        help="Choose the full suite or one test category.",
    )
    arguments, pytest_arguments = parser.parse_known_args()

    command = [sys.executable, "-m", "pytest", "tests"]
    if arguments.suite != "all":
        command.extend(["-m", arguments.suite])
    command.extend(pytest_arguments)

    return subprocess.call(command, cwd=Path(__file__).resolve().parent)


if __name__ == "__main__":
    raise SystemExit(main())
