"""
agents/long_to_shorts/api/server.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Convenience entry-point to start the LongToShorts FastAPI server with
uvicorn.

Usage
-----
    # From the project root
    python agents/long_to_shorts/api/server.py

    # Or explicitly with custom host/port
    python agents/long_to_shorts/api/server.py --host 0.0.0.0 --port 8080

    # Or via uvicorn directly (supports --reload for development)
    uvicorn agents.long_to_shorts.api.app:app --reload --port 8000

Configuration
-------------
    HOST    env var or --host flag   (default: 127.0.0.1)
    PORT    env var or --port flag   (default: 8000)
    LOG_LEVEL                        (default: info)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ── Ensure project root is on sys.path when run directly ──────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[4]  # …/YTShortsEnginer
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── Load .env before importing heavy modules ──────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass  # python-dotenv optional (env vars may be set by the shell)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="long-to-shorts-api",
        description="Start the LongToShorts FastAPI server.",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", "127.0.0.1"),
        help="Bind address (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "8000")),
        help="Port to listen on (default: 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=False,
        help="Enable hot-reload (development only)",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "info"),
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="Uvicorn log level (default: info)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    try:
        import uvicorn
    except ImportError:
        print(
            "ERROR: uvicorn is not installed.\n"
            "Run:  pip install 'uvicorn[standard]'",
            file=sys.stderr,
        )
        sys.exit(1)

    print(
        f"\n  LongToShorts API\n"
        f"  http://{args.host}:{args.port}/docs  ← Swagger UI\n"
        f"  http://{args.host}:{args.port}/redoc ← ReDoc UI\n"
    )

    uvicorn.run(
        "agents.long_to_shorts.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
