"""
Run FastAPI locally (venv, no Docker).

  cd backend
  python run_server.py

Optional:
  python run_server.py --skip-migrations
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


def main() -> None:
    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root)

    parser = argparse.ArgumentParser(description="Run medical-constructor API with uvicorn.")
    parser.add_argument(
        "--skip-migrations",
        action="store_true",
        help="Do not run alembic upgrade head before starting.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8012)
    parser.add_argument("--no-reload", action="store_true", help="Disable autoreload.")
    args = parser.parse_args()

    if not args.skip_migrations:
        r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"])
        if r.returncode != 0:
            print(
                "alembic upgrade failed (check Postgres and DATABASE_URL in .env). "
                "Start anyway with: python run_server.py --skip-migrations",
                file=sys.stderr,
            )
            sys.exit(r.returncode)

    try:
        import uvicorn
    except ImportError as e:
        print("Install dependencies: pip install -r requirements.txt", file=sys.stderr)
        raise SystemExit(1) from e

    print(f"OpenAPI: http://{args.host}:{args.port}/docs")
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
    )


if __name__ == "__main__":
    main()
