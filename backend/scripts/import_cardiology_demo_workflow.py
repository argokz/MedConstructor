"""
Import the latest cardiology benchmark into the normal demo learning workflow.

Usage:
  cd backend
  .venv\Scripts\python.exe scripts\import_cardiology_demo_workflow.py

Demo-account passwords are taken from DEMO_TEACHER_PASSWORD / DEMO_STUDENT_PASSWORD
(local/dev only); in production a strong random password is generated and existing
account passwords are left untouched.

The script creates or updates:
- the demo teacher and demo student accounts (teacher@demo.local, student@demo.local)
- cardiology demo group and targets
- 12 assignments with reference graphs
- 73 student attempts with automatic metrics and teacher recommendations
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import AsyncSessionLocal
from app.services.demo_cardiology_importer import import_cardiology_demo_workflow


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK = BACKEND_ROOT / "benchmarks" / "cardiology_synthetic_latest.json"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Import cardiology benchmark into demo teacher/student workflow.")
    parser.add_argument("--benchmark", default=str(DEFAULT_BENCHMARK), help="Path to cardiology_synthetic_latest.json")
    parser.add_argument(
        "--keep-created-at",
        action="store_true",
        help="Do not refresh created_at timestamps on existing demo attempts.",
    )
    args = parser.parse_args()

    benchmark_path = Path(args.benchmark).resolve()
    async with AsyncSessionLocal() as session:
        result = await import_cardiology_demo_workflow(
            session,
            benchmark_path=benchmark_path,
            refresh_timestamps=not args.keep_created_at,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
