"""Container healthcheck: `python -m app.healthcheck` exits 0 when healthy.

Unhealthy when a mounted folder is missing or the main loop hasn't touched
its heartbeat file recently (hung or crashed).
"""
import os
import sys
import time

from .config import settings


def check() -> list:
    problems = []
    for name, path in (
        ("DOWNLOAD_DIR", settings.input_dir),
        ("MOVIE_OUTPUT", settings.output_dir),
        ("STATE_DIR", os.path.dirname(settings.state_file)),
    ):
        if not os.path.isdir(path):
            problems.append(f"{name} {path} is not a directory")

    try:
        age = time.time() - os.path.getmtime(settings.heartbeat_file)
    except OSError:
        problems.append(f"heartbeat file {settings.heartbeat_file} is missing")
    else:
        if age > settings.heartbeat_max_age_seconds:
            problems.append(
                f"heartbeat is {int(age)}s old (max {settings.heartbeat_max_age_seconds}s)"
            )
    return problems


def main() -> int:
    problems = check()
    for problem in problems:
        print(f"UNHEALTHY: {problem}")
    if not problems:
        print("OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
