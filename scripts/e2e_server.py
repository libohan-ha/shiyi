"""Serve the real build against a fresh, disposable database for browser tests."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    port = int(os.environ.get("SHIYI_E2E_PORT", "18765"))
    os.chdir(root / "backend")
    with tempfile.TemporaryDirectory(prefix="shiyi-e2e-") as directory:
        os.environ.update({
            "SHIYI_DATA_DIR": directory,
            "SHIYI_DATABASE_URL": "sqlite:///" + (Path(directory) / "test.db").as_posix(),
            "SHIYI_PUBLIC_URL": f"http://127.0.0.1:{port}",
            "SHIYI_ALLOWED_ORIGINS": f"http://shiyi-lan.test:{port}",
            "SHIYI_SECURE_COOKIES": "false",
            "SHIYI_ALLOW_REGISTRATION": "true",
            "SHIYI_TRUSTED_HOSTS": "localhost,127.0.0.1,testserver,shiyi-lan.test",
            "SHIYI_FRONTEND_DIR": os.environ.get("SHIYI_E2E_FRONTEND_DIR", str(root / "frontend" / "dist")),
        })
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
        import uvicorn

        sys.path.insert(0, str(root / "backend"))
        from app.database import engine

        try:
            uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="warning")
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
