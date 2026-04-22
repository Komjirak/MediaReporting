"""MediaReporting 웹 대시보드 - Flask"""
import importlib
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template, request, redirect, url_for, jsonify, abort
import config
from storage import database as db
from web.ranking import rank_articles

app = Flask(__name__, template_folder="templates", static_folder="static")
KST = timezone(timedelta(hours=9))

_IS_VERCEL = bool(os.environ.get("VERCEL"))
_USE_PG    = bool(os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL"))


def _kst_now_str():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")


def _today():
    return datetime.now(KST).strftime("%Y-%m-%d")


# ── 설정 읽기/쓰기 ───────────────────────────────────────────
# Postgres 모드: app_settings 테이블 사용 (영구 저장)
# SQLite 모드 : .env 파일 사용 (로컬 개발)

_ENV_PATH = Path(__file__).parent.parent / ".env"


def _load_settings() -> dict:
    """현재 설정을 dict 로 반환 (표시용)"""
    if _USE_PG:
        data = db.get_all_settings()
        # DB 에 없는 값은 환경변수(Vercel 대시보드 env)에서 보충
        _fallbacks = [
            "COMPANY_NAME", "KEYWORDS",
            "RISK_KEYWORDS_HIGH", "RISK_KEYWORDS_CRITICAL",
            "MONITOR_INTERVAL_SECONDS", "COLLECT_HOURS_BACK",
            "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET",
            "GEMINI_API_KEY", "Gemini_API_KEY",
            "SLACK_WEBHOOK_URL", "SMTP_USER",
        ]
        for k in _fallbacks:
            if k not in data and os.environ.get(k):
                data[k] = os.environ[k]
        return data
    else:
        # SQLite 로컬: .env 파일 읽기
        data = {}
        if _ENV_PATH.exists():
            for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    data[k.strip()] = v.strip()
        return data


def _save_settings(updates: dict):
    """설정을 저장하고 config 모듈을 즉시 갱신"""
    if _USE_PG:
        db.save_settings(updates)
    else:
        # .env 파일 업데이트
        current = _load_settings()
        current.update(updates)
        lines = [f"{k}={v}" for k, v in current.items()]
        try:
            _ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except PermissionError:
            Path("/tmp/.env").write_text("\n".join(lines) + "\n", encoding="utf-8")
        from dotenv import load_dotenv
        load_dotenv(_ENV_PATH, override=True)

    # os.environ 및 config 모듈 즉시 반영
    for k, v in updates.items():
        os.environ[k] = v
    importlib.reload(config)


# ── 라우트 ───────────────────────────────────────────────────

@app.route("/")
def dashboard():
    today = _today()
    daily = db.get_daily_log(today)

    from datetime import date, timedelta as td
    history = []
    for i in range(7):
        d = (date.today() - td(days=i)).isoformat()
        log = db.get_daily_log(d)
        if log:
            history.append(log)

    articles = db.get_articles_in_window(hours_back=24)
    articles = rank_articles(articles)

    html_reports = sorted(
        Path(config.REPORTS_HTML_DIR).glob("*.html"),
        reverse=True
    )[:10]
    reports = [{"name": p.stem, "path": f"/report/{p.name}"} for p in html_reports]

    return render_template(
        "index.html",
        company=config.COMPANY_NAME,
        keywords=config.KEYWORDS,
        now=_kst_now_str(),
        today=today,
        daily=daily,
        history=history,
        articles=articles[:50],
        reports=reports,
    )


@app.route("/feed")
def feed():
    """Slack 스타일 일별 기사 피드"""
    date_str = request.args.get("date", _today())
    keyword_filter = request.args.get("kw", "")
    risk_filter = request.args.get("risk", "")

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=KST)
        next_dt = dt + timedelta(days=1)
        with db._conn() as con:
            rows = con.execute(
                "SELECT * FROM articles WHERE collected_at >= ? AND collected_at < ? ORDER BY published_at DESC",
                (dt.isoformat(), next_dt.isoformat())
            ).fetchall()
        articles = rows
    except Exception:
        articles = db.get_articles_in_window(hours_back=24)

    if keyword_filter:
        articles = [a for a in articles if keyword_filter in a.get("keyword", "")]
    if risk_filter:
        articles = [a for a in articles if a.get("risk_level") == risk_filter]

    articles = rank_articles(articles)

    recent_runs = db.get_recent_run_stats(hours=24 * 14)
    dates = sorted({r["started_at"][:10] for r in recent_runs}, reverse=True)

    return render_template(
        "feed.html",
        company=config.COMPANY_NAME,
        now=_kst_now_str(),
        date_str=date_str,
        articles=articles,
        dates=dates,
        keyword_filter=keyword_filter,
        risk_filter=risk_filter,
        keywords=config.KEYWORDS,
    )


@app.route("/settings", methods=["GET", "POST"])
def settings():
    env = _load_settings()
    saved = False
    errors = []

    if request.method == "POST":
        company = request.form.get("company_name", "").strip()
        keywords_raw = request.form.get("keywords", "").strip()
        risk_high = request.form.get("risk_high", "").strip()
        risk_critical = request.form.get("risk_critical", "").strip()
        monitor_interval = request.form.get("monitor_interval", "300").strip()
        collect_hours = request.form.get("collect_hours", "6").strip()

        if not company:
            errors.append("회사명을 입력해주세요.")
        if not keywords_raw:
            errors.append("키워드를 최소 1개 입력해주세요.")

        if not errors:
            _save_settings({
                "COMPANY_NAME": company,
                "KEYWORDS": keywords_raw,
                "RISK_KEYWORDS_HIGH": risk_high,
                "RISK_KEYWORDS_CRITICAL": risk_critical,
                "MONITOR_INTERVAL_SECONDS": monitor_interval,
                "COLLECT_HOURS_BACK": collect_hours,
            })
            env = _load_settings()
            saved = True

    return render_template(
        "settings.html",
        company=config.COMPANY_NAME,
        now=_kst_now_str(),
        env=env,
        saved=saved,
        errors=errors,
        is_vercel=_IS_VERCEL,
        use_pg=_USE_PG,
    )


@app.route("/report/<filename>")
def report_view(filename):
    """저장된 HTML 리포트 서빙"""
    report_path = Path(config.REPORTS_HTML_DIR) / filename
    if not report_path.exists() or not filename.endswith(".html"):
        abort(404)
    return report_path.read_text(encoding="utf-8")


@app.route("/api/articles")
def api_articles():
    hours = int(request.args.get("hours", 24))
    risk = request.args.get("risk", "")
    articles = db.get_articles_in_window(hours_back=hours)
    if risk:
        articles = [a for a in articles if a.get("risk_level") == risk]
    articles = rank_articles(articles)
    return jsonify(articles[:100])


@app.route("/api/daily/<date_str>")
def api_daily(date_str):
    log = db.get_daily_log(date_str)
    if not log:
        return jsonify({"error": "not found"}), 404
    return jsonify(log)


from web.pipeline_status import status as _ps


def _start_pipeline(label: str):
    from datetime import datetime as _dt
    import threading
    _ps["running"] = True
    _ps["step"] = "시작 중"
    _ps["step_num"] = 0
    _ps["detail"] = ""
    _ps["started_at"] = _dt.now(KST).strftime("%H:%M:%S")
    _ps["finished_at"] = ""

    def _run():
        try:
            from scheduler.jobs import run_full_pipeline
            run_full_pipeline(label)
        finally:
            _ps["running"] = False
            _ps["step"] = "완료"
            _ps["finished_at"] = datetime.now(KST).strftime("%H:%M:%S")

    threading.Thread(target=_run, daemon=True).start()


@app.route("/api/run-now", methods=["POST"])
def api_run_now():
    if _ps["running"]:
        return jsonify({"status": "already_running"})
    _start_pipeline("웹 즉시 실행")
    return jsonify({"status": "started"})


@app.route("/api/run-status", methods=["GET"])
def api_run_status():
    return jsonify({
        "running":     _ps["running"],
        "step":        _ps["step"],
        "step_num":    _ps["step_num"],
        "total_steps": _ps["total_steps"],
        "detail":      _ps["detail"],
        "started_at":  _ps["started_at"],
        "finished_at": _ps["finished_at"],
        "last_result": _ps["last_result"],
    })


@app.route("/api/reset-and-run", methods=["POST"])
def api_reset_and_run():
    if _ps["running"]:
        return jsonify({"status": "already_running"})
    deleted = db.clear_all_articles()
    _start_pipeline("웹 초기화 후 수집")
    return jsonify({"status": "started", "deleted": deleted})


if __name__ == "__main__":
    db.init_db()
    port = int(os.environ.get("PORT", 5100))
    app.run(host="0.0.0.0", port=port, debug=False)
