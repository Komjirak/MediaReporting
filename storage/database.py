"""SQLite 데이터베이스 래퍼 - 모든 DB 로직을 여기서 관리"""
import sqlite3
import hashlib
import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional

import config

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _kst_now() -> str:
    return datetime.now(KST).isoformat()


@contextmanager
def _conn():
    con = sqlite3.connect(config.DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db():
    """테이블 초기화 (없으면 생성)"""
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash            TEXT UNIQUE NOT NULL,
            url                 TEXT NOT NULL,
            title               TEXT NOT NULL,
            title_normalized    TEXT NOT NULL,
            source              TEXT NOT NULL,
            keyword             TEXT NOT NULL,
            published_at        TEXT NOT NULL,
            collected_at        TEXT NOT NULL,
            summary_ko          TEXT,
            risk_level          TEXT DEFAULT 'LOW',
            risk_reason         TEXT,
            category            TEXT,
            run_id              TEXT,
            notified            INTEGER DEFAULT 0,
            included_in_report  INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS report_runs (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id              TEXT UNIQUE NOT NULL,
            run_type            TEXT NOT NULL,
            started_at          TEXT NOT NULL,
            completed_at        TEXT,
            article_count       INTEGER DEFAULT 0,
            new_article_count   INTEGER DEFAULT 0,
            audit_flags         TEXT,
            report_html_path    TEXT,
            report_md_path      TEXT
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      TEXT NOT NULL,
            checked_at  TEXT NOT NULL,
            flag_type   TEXT NOT NULL,
            flag_detail TEXT NOT NULL,
            severity    TEXT NOT NULL,
            resolved    INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_articles_collected  ON articles(collected_at);
        CREATE INDEX IF NOT EXISTS idx_articles_risk       ON articles(risk_level);
        CREATE INDEX IF NOT EXISTS idx_articles_run_id     ON articles(run_id);
        CREATE INDEX IF NOT EXISTS idx_articles_notified   ON articles(notified);

        -- 일단위 모니터링 누적 기록
        CREATE TABLE IF NOT EXISTS daily_monitoring_log (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            log_date         TEXT UNIQUE NOT NULL,   -- YYYY-MM-DD (KST)
            total_articles   INTEGER DEFAULT 0,
            critical_count   INTEGER DEFAULT 0,
            high_count       INTEGER DEFAULT 0,
            medium_count     INTEGER DEFAULT 0,
            low_count        INTEGER DEFAULT 0,
            keywords_coverage TEXT,   -- JSON: {keyword: {naver: N, google: N}}
            top_articles     TEXT,    -- JSON: CRITICAL/HIGH 기사 목록 (상위 10건)
            audit_flags      TEXT,    -- JSON: 당일 감사 플래그 목록
            sources_used     TEXT,    -- JSON: ["Naver News", "Google News"]
            run_count        INTEGER DEFAULT 0,  -- 당일 스케줄 실행 횟수
            notes            TEXT,    -- 수동 메모
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_daily_log_date ON daily_monitoring_log(log_date);
        CREATE VIRTUAL TABLE IF NOT EXISTS daily_log_fts USING fts5(
            log_date, top_articles, audit_flags, notes,
            tokenize='unicode61'
        );
        """)
    logger.info("DB initialized: %s", config.DB_PATH)


# ── URL 해시 ─────────────────────────────────────────────────

def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def is_duplicate(url: str) -> bool:
    h = url_hash(url)
    with _conn() as con:
        row = con.execute(
            "SELECT 1 FROM articles WHERE url_hash=? LIMIT 1", (h,)
        ).fetchone()
    return row is not None


# ── 기사 저장/조회 ────────────────────────────────────────────

def insert_article(article: dict, run_id: str = "") -> bool:
    """새 기사를 저장. 중복이면 False 반환."""
    h = url_hash(article["url"])
    try:
        with _conn() as con:
            con.execute("""
            INSERT OR IGNORE INTO articles
                (url_hash, url, title, title_normalized, source, keyword,
                 published_at, collected_at, summary_ko, risk_level,
                 risk_reason, category, run_id, notified, included_in_report)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0,0)
            """, (
                h,
                article["url"],
                article["title"],
                article.get("title_normalized", article["title"].lower()),
                article["source"],
                article.get("keyword", ""),
                article.get("published_at", _kst_now()),
                article.get("collected_at", _kst_now()),
                article.get("summary_ko"),
                article.get("risk_level", "LOW"),
                article.get("risk_reason"),
                article.get("category"),
                run_id,
            ))
        return True
    except sqlite3.IntegrityError:
        return False


def update_article_summary(url: str, summary_ko: str, risk_level: str,
                            risk_reason: str, category: str):
    """Claude 요약 결과 업데이트"""
    h = url_hash(url)
    with _conn() as con:
        con.execute("""
        UPDATE articles
        SET summary_ko=?, risk_level=?, risk_reason=?, category=?
        WHERE url_hash=?
        """, (summary_ko, risk_level, risk_reason, category, h))


def get_articles_for_run(run_id: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM articles WHERE run_id=? ORDER BY risk_level DESC, published_at DESC",
            (run_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_articles_without_summary(hours_back: int = 24, limit: int = 200) -> list[dict]:
    """요약이 없는 기사 조회 - 재요약 대상"""
    cutoff = (datetime.now(KST) - timedelta(hours=hours_back)).isoformat()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM articles WHERE (summary_ko IS NULL OR summary_ko='') "
            "AND collected_at >= ? ORDER BY risk_level DESC, published_at DESC LIMIT ?",
            (cutoff, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def get_articles_in_window(hours_back: int = 6) -> list[dict]:
    cutoff = (datetime.now(KST) - timedelta(hours=hours_back)).isoformat()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM articles WHERE collected_at >= ? ORDER BY published_at DESC",
            (cutoff,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_unnotified_high_risk() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM articles WHERE notified=0 AND risk_level IN ('CRITICAL','HIGH')"
            " ORDER BY risk_level DESC, collected_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def mark_notified(article_ids: list[int]):
    if not article_ids:
        return
    placeholders = ",".join("?" * len(article_ids))
    with _conn() as con:
        con.execute(
            f"UPDATE articles SET notified=1 WHERE id IN ({placeholders})",
            article_ids
        )


def mark_included_in_report(article_ids: list[int]):
    if not article_ids:
        return
    placeholders = ",".join("?" * len(article_ids))
    with _conn() as con:
        con.execute(
            f"UPDATE articles SET included_in_report=1 WHERE id IN ({placeholders})",
            article_ids
        )


def get_keyword_counts_by_source(hours_back: int = 24) -> dict:
    """감사용: 키워드별/소스별 기사 수"""
    cutoff = (datetime.now(KST) - timedelta(hours=hours_back)).isoformat()
    with _conn() as con:
        rows = con.execute("""
        SELECT keyword, source, COUNT(*) as cnt
        FROM articles
        WHERE collected_at >= ?
        GROUP BY keyword, source
        """, (cutoff,)).fetchall()
    result: dict[str, dict[str, int]] = {}
    for r in rows:
        result.setdefault(r["keyword"], {})[r["source"]] = r["cnt"]
    return result


def get_recent_run_stats(hours: int = 48) -> list[dict]:
    cutoff = (datetime.now(KST) - timedelta(hours=hours)).isoformat()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM report_runs WHERE started_at >= ? ORDER BY started_at DESC",
            (cutoff,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── 리포트 런 ─────────────────────────────────────────────────

def create_run(run_id: str, run_type: str) -> str:
    with _conn() as con:
        con.execute("""
        INSERT OR IGNORE INTO report_runs (run_id, run_type, started_at)
        VALUES (?,?,?)
        """, (run_id, run_type, _kst_now()))
    return run_id


def complete_run(run_id: str, article_count: int, new_article_count: int,
                 audit_flags: list, html_path: str = "", md_path: str = ""):
    with _conn() as con:
        con.execute("""
        UPDATE report_runs
        SET completed_at=?, article_count=?, new_article_count=?,
            audit_flags=?, report_html_path=?, report_md_path=?
        WHERE run_id=?
        """, (
            _kst_now(),
            article_count,
            new_article_count,
            json.dumps(audit_flags, ensure_ascii=False),
            html_path,
            md_path,
            run_id,
        ))


# ── 감사 로그 ─────────────────────────────────────────────────

def insert_audit_flag(run_id: str, flag_type: str, flag_detail: str, severity: str):
    with _conn() as con:
        con.execute("""
        INSERT INTO audit_log (run_id, checked_at, flag_type, flag_detail, severity)
        VALUES (?,?,?,?,?)
        """, (run_id, _kst_now(), flag_type, flag_detail, severity))


def get_audit_flags_for_run(run_id: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM audit_log WHERE run_id=? ORDER BY severity DESC",
            (run_id,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── 일단위 모니터링 로그 ──────────────────────────────────────────

def upsert_daily_log(articles: list[dict], audit_flags: list[dict],
                     run_count_delta: int = 1, notes: str = ""):
    """
    당일 모니터링 기록을 DB에 누적 저장 (UPSERT).
    하루에 여러 번 실행되므로 기존 레코드가 있으면 합산 업데이트.
    """
    today = datetime.now(KST).strftime("%Y-%m-%d")
    now = _kst_now()

    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for a in articles:
        lvl = a.get("risk_level", "LOW")
        counts[lvl] = counts.get(lvl, 0) + 1

    # CRITICAL/HIGH 기사 상위 10건 직렬화
    top = [
        {"title": a["title"], "url": a["url"], "risk_level": a.get("risk_level", "LOW"),
         "source": a.get("source", ""), "published_at": a.get("published_at", ""),
         "summary_ko": a.get("summary_ko", ""), "risk_reason": a.get("risk_reason", "")}
        for a in articles
        if a.get("risk_level") in ("CRITICAL", "HIGH")
    ][:10]

    sources = list({a.get("source", "") for a in articles if a.get("source")})
    kw_coverage = get_keyword_counts_by_source(hours_back=24)

    with _conn() as con:
        existing = con.execute(
            "SELECT * FROM daily_monitoring_log WHERE log_date=?", (today,)
        ).fetchone()

        if existing:
            # 기존 레코드에 합산
            prev_top = json.loads(existing["top_articles"] or "[]")
            existing_urls = {t["url"] for t in prev_top}
            merged_top = prev_top + [t for t in top if t["url"] not in existing_urls]
            merged_top = sorted(
                merged_top,
                key=lambda x: ["CRITICAL", "HIGH", "MEDIUM", "LOW"].index(x.get("risk_level", "LOW"))
            )[:10]

            prev_flags = json.loads(existing["audit_flags"] or "[]")
            all_flags = prev_flags + audit_flags  # 누적 감사 플래그

            con.execute("""
            UPDATE daily_monitoring_log SET
                total_articles   = total_articles + ?,
                critical_count   = critical_count + ?,
                high_count       = high_count + ?,
                medium_count     = medium_count + ?,
                low_count        = low_count + ?,
                keywords_coverage = ?,
                top_articles     = ?,
                audit_flags      = ?,
                sources_used     = ?,
                run_count        = run_count + ?,
                notes            = CASE WHEN ? != '' THEN ? ELSE notes END,
                updated_at       = ?
            WHERE log_date = ?
            """, (
                len(articles),
                counts["CRITICAL"], counts["HIGH"], counts["MEDIUM"], counts["LOW"],
                json.dumps(kw_coverage, ensure_ascii=False),
                json.dumps(merged_top, ensure_ascii=False),
                json.dumps(all_flags, ensure_ascii=False),
                json.dumps(sources, ensure_ascii=False),
                run_count_delta,
                notes, notes,
                now, today,
            ))
        else:
            con.execute("""
            INSERT INTO daily_monitoring_log
                (log_date, total_articles, critical_count, high_count, medium_count,
                 low_count, keywords_coverage, top_articles, audit_flags, sources_used,
                 run_count, notes, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                today,
                len(articles),
                counts["CRITICAL"], counts["HIGH"], counts["MEDIUM"], counts["LOW"],
                json.dumps(kw_coverage, ensure_ascii=False),
                json.dumps(top, ensure_ascii=False),
                json.dumps(audit_flags, ensure_ascii=False),
                json.dumps(sources, ensure_ascii=False),
                run_count_delta,
                notes, now, now,
            ))

        # FTS 인덱스 동기화 (독립 FTS 테이블)
        row = con.execute("SELECT * FROM daily_monitoring_log WHERE log_date=?", (today,)).fetchone()
        if row:
            # 기존 FTS 항목 삭제 후 재삽입
            con.execute("DELETE FROM daily_log_fts WHERE log_date=?", (today,))
            con.execute(
                "INSERT INTO daily_log_fts(log_date, top_articles, audit_flags, notes) VALUES (?,?,?,?)",
                (row["log_date"], row["top_articles"] or "", row["audit_flags"] or "", row["notes"] or "")
            )

    logger.info("[DailyLog] %s 기록 업데이트: 총 %d건", today, len(articles))


def get_daily_log(date_str: str) -> Optional[dict]:
    """특정 날짜(YYYY-MM-DD) 일간 로그 조회"""
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM daily_monitoring_log WHERE log_date=?", (date_str,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    for field in ("keywords_coverage", "top_articles", "audit_flags", "sources_used"):
        if d.get(field):
            try:
                d[field] = json.loads(d[field])
            except Exception:
                pass
    return d


def get_daily_logs_range(start_date: str, end_date: str) -> list[dict]:
    """날짜 범위(YYYY-MM-DD) 일간 로그 조회"""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM daily_monitoring_log WHERE log_date BETWEEN ? AND ? ORDER BY log_date DESC",
            (start_date, end_date)
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        for field in ("keywords_coverage", "top_articles", "audit_flags", "sources_used"):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except Exception:
                    pass
        result.append(d)
    return result


def search_daily_logs(query: str, limit: int = 20) -> list[dict]:
    """
    일간 로그 전문 검색 (FTS5).
    query: 검색어 (예: "소송", "CRITICAL", "2026-04")
    """
    with _conn() as con:
        try:
            # FTS5 검색
            fts_rows = con.execute(
                "SELECT log_date FROM daily_log_fts WHERE daily_log_fts MATCH ? ORDER BY rank LIMIT ?",
                (query, limit)
            ).fetchall()
            dates = [r["log_date"] for r in fts_rows]
            if dates:
                placeholders = ",".join("?" * len(dates))
                rows = con.execute(
                    f"SELECT * FROM daily_monitoring_log WHERE log_date IN ({placeholders}) ORDER BY log_date DESC",
                    dates
                ).fetchall()
            else:
                rows = []
        except Exception:
            # FTS 실패 시 LIKE 폴백
            rows = con.execute("""
            SELECT * FROM daily_monitoring_log
            WHERE log_date LIKE ? OR top_articles LIKE ? OR audit_flags LIKE ? OR notes LIKE ?
            ORDER BY log_date DESC LIMIT ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", limit)).fetchall()

    result = []
    for row in rows:
        d = dict(row)
        for field in ("keywords_coverage", "top_articles", "audit_flags", "sources_used"):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except Exception:
                    pass
        result.append(d)
    return result


def clear_all_articles():
    """기사 전체 삭제 (키워드 변경 후 초기화용)"""
    with _conn() as con:
        deleted = con.execute("DELETE FROM articles").rowcount
        con.execute("DELETE FROM daily_monitoring_log")
        con.execute("DELETE FROM daily_log_fts")
        con.execute("DELETE FROM report_runs")
        con.execute("DELETE FROM audit_log")
    logger.info("[DB] 전체 초기화 완료: 기사 %d건 삭제", deleted)
    return deleted


def add_daily_note(date_str: str, note: str):
    """특정 날짜에 수동 메모 추가"""
    now = _kst_now()
    with _conn() as con:
        con.execute("""
        UPDATE daily_monitoring_log
        SET notes = CASE WHEN notes IS NULL OR notes = '' THEN ? ELSE notes || char(10) || ? END,
            updated_at = ?
        WHERE log_date = ?
        """, (note, note, now, date_str))
        # FTS 재동기화
        row = con.execute(
            "SELECT * FROM daily_monitoring_log WHERE log_date=?", (date_str,)
        ).fetchone()
        if row:
            con.execute("DELETE FROM daily_log_fts WHERE log_date=?", (date_str,))
            con.execute(
                "INSERT INTO daily_log_fts(log_date, top_articles, audit_flags, notes) VALUES (?,?,?,?)",
                (row["log_date"], row["top_articles"] or "", row["audit_flags"] or "", row["notes"] or "")
            )
    logger.info("[DailyLog] %s 메모 추가: %s", date_str, note[:50])
