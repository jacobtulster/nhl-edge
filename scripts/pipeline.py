#!/usr/bin/env python3
"""
Hourly entrypoint: refresh DB → run model → publish EV board.
Skips outside 8am–11pm Eastern unless --force is passed.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nhl_edge.schedule_window import within_run_window


def _run(script: str) -> None:
    path = ROOT / "scripts" / script
    print(f"\n=== Running {script} ===")
    subprocess.run([sys.executable, str(path)], check=True, cwd=str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="NHL Edge hourly pipeline")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even outside the 8am–11pm Eastern window",
    )
    args = parser.parse_args()

    ok, message = within_run_window()
    print(message)
    if not ok and not args.force:
        return 0

    _run("refresh_database.py")
    _run("run_model.py")
    print("\nPipeline complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
