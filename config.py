"""중앙 설정 모듈 - 모든 튜닝 가능한 값은 여기서 관리"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── 디렉토리 경로 ──────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
LOGS_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "articles.db"
REPORTS_HTML_DIR = REPORTS_DIR / "html"
REPORTS_MD_DIR = REPORTS_DIR / "markdown"

# 디렉토리 자동 생성
for d in [DATA_DIR, REPORTS_HTML_DIR, REPORTS_MD_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── 회사/키워드 설정 ────────────────────────────────────────
COMPANY_NAME = os.getenv("COMPANY_NAME", "회사명")

_kw_raw = os.getenv("KEYWORDS", COMPANY_NAME)
KEYWORDS: list[str] = [k.strip() for k in _kw_raw.split(",") if k.strip()]

_risk_high_raw = os.getenv("RISK_KEYWORDS_HIGH", "소송,벌금,리콜,수사,징계,사고,구속,기소")
RISK_KEYWORDS_HIGH: list[str] = [k.strip() for k in _risk_high_raw.split(",") if k.strip()]

_risk_crit_raw = os.getenv("RISK_KEYWORDS_CRITICAL", "기소,구속,파산,대규모사고,사망")
RISK_KEYWORDS_CRITICAL: list[str] = [k.strip() for k in _risk_crit_raw.split(",") if k.strip()]

# ── API 자격증명 ────────────────────────────────────────────
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")  # 미사용 (Gemini로 전환)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY", "")

# ── 이메일 설정 ─────────────────────────────────────────────
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
_recipients = os.getenv("EMAIL_RECIPIENTS", "")
EMAIL_RECIPIENTS: list[str] = [r.strip() for r in _recipients.split(",") if r.strip()]

# ── Slack 설정 ──────────────────────────────────────────────
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

# ── 스케줄 설정 (KST 기준) ─────────────────────────────────
SCHEDULE_TIMES_KST = [
    {"hour": 3,  "minute": 0, "label": "03시 정기"},
    {"hour": 9,  "minute": 0, "label": "09시 정기"},
    {"hour": 15, "minute": 0, "label": "15시 정기"},
]

# ── 모니터링 설정 ───────────────────────────────────────────
MONITOR_INTERVAL_SECONDS = int(os.getenv("MONITOR_INTERVAL_SECONDS", "300"))
AUDIT_MIN_ARTICLES = int(os.getenv("AUDIT_MIN_ARTICLES", "3"))

# ── 수집 설정 ───────────────────────────────────────────────
GOOGLE_NEWS_RSS_TEMPLATE = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
NAVER_NEWS_API_URL = "https://openapi.naver.com/v1/search/news.json"
NAVER_DISPLAY = 50          # 키워드당 최대 수집 건수
COLLECT_HOURS_BACK = 6      # 최근 N시간 기사만 수집 (스케줄 주기에 맞게)

# ── 중복 제거 설정 ──────────────────────────────────────────
DEDUP_TITLE_SIMILARITY_THRESHOLD = 0.80  # 제목 유사도 임계값

# ── Gemini 모델 ─────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.5-flash"  # 최신 안정 Flash 모델
SUMMARIZE_MAX_TOKENS = 1024

# ── 로깅 설정 ───────────────────────────────────────────────
LOG_FILE = LOGS_DIR / "media_report.log"
LOG_MAX_BYTES = 10 * 1024 * 1024   # 10MB
LOG_BACKUP_COUNT = 5
