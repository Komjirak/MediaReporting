from pathlib import Path
import sys
import os

# Ensure project root is importable in Vercel runtime.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage import database as db
db.init_db()

# Vercel Postgres 모드: app_settings 에서 설정을 읽어 os.environ 에 반영한 뒤 config 재로드
if os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL"):
    try:
        settings = db.get_all_settings()
        if settings:
            for k, v in settings.items():
                os.environ[k] = v
            import importlib
            import config as _cfg
            importlib.reload(_cfg)
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("Startup settings load failed: %s", _e)

from web.app import app

# Vercel Python runtime expects a module-level variable named `app`.
