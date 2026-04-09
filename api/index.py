from pathlib import Path
import sys

# Ensure project root is importable in Vercel runtime.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage import database as db
from web.app import app

db.init_db()

# Vercel Python runtime expects a module-level variable named `app`.
