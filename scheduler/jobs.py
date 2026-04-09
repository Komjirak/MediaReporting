"""APScheduler 스케줄 잡 정의 및 전체 파이프라인"""
import logging
import uuid
from datetime import datetime, timezone, timedelta

from collectors import google_news, naver_news
from processors import classifier, deduplicator, summarizer
from storage import database as db
from audit import reviewer
from reporters import html_reporter, markdown_reporter
from notifiers import email_notifier, slack_notifier
import config

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def run_full_pipeline(run_label: str):
    """
    전체 미디어 리포팅 파이프라인:
    수집 → 중복제거 → 분류 → 요약(Gemini) → 저장 → 감사 → 리포트 생성 → 발송
    """
    try:
        from web.pipeline_status import status, update
        _has_status = True
    except ImportError:
        _has_status = False

    def _update(step_num, step, detail=""):
        if _has_status:
            update(step_num, step, detail)
        logger.info("[Pipeline] %s %s", step, detail)

    run_id = f"{datetime.now(KST).strftime('%Y%m%d_%H%M')}_{uuid.uuid4().hex[:6]}"
    logger.info("=== 파이프라인 시작: %s [run_id=%s] ===", run_label, run_id)

    db.create_run(run_id, run_type=run_label)

    try:
        # ── 1. 수집 ──────────────────────────────────────────
        _update(1, "뉴스 수집 중", "Google + Naver")
        google_articles = google_news.collect(hours_back=config.COLLECT_HOURS_BACK)
        naver_articles  = naver_news.collect(hours_back=config.COLLECT_HOURS_BACK)
        all_articles = google_articles + naver_articles
        _update(1, "뉴스 수집 중", f"Google {len(google_articles)}건 + Naver {len(naver_articles)}건")

        # ── 2. 중복 제거 ──────────────────────────────────────
        _update(2, "중복 제거 중", f"총 {len(all_articles)}건")
        unique_articles = deduplicator.deduplicate(all_articles)
        _update(2, "중복 제거 중", f"→ 신규 {len(unique_articles)}건")

        # ── 3. 키워드 기반 리스크 분류 (빠른 사전 분류) ────────
        _update(3, "리스크 분류 중", f"{len(unique_articles)}건")
        for art in unique_articles:
            art["risk_level"], art["risk_reason"] = classifier.classify_risk(art)
            art["category"] = classifier.classify_category(art)

        # ── 4. Gemini 요약 ────────────────────────────────────
        _update(4, "AI 요약 중", f"{len(unique_articles)}건 (시간이 걸릴 수 있어요)")
        summarized = summarizer.summarize_batch(unique_articles)

        # ── 5. DB 저장 ────────────────────────────────────────
        _update(5, "DB 저장 중", "")
        new_count = 0
        for art in summarized:
            inserted = db.insert_article(art, run_id=run_id)
            if inserted:
                new_count += 1
            else:
                db.update_article_summary(
                    art["url"],
                    art.get("summary_ko", ""),
                    art.get("risk_level", "LOW"),
                    art.get("risk_reason", ""),
                    art.get("category", "기타"),
                )

        # ── 5-1. 기존 미요약 기사 재요약 ────
        unsummarized = db.get_articles_without_summary(hours_back=24)
        if unsummarized:
            _update(5, "DB 저장 중", f"미요약 {len(unsummarized)}건 재요약")
            re_summarized = summarizer.summarize_batch(unsummarized)
            for art in re_summarized:
                db.update_article_summary(
                    art["url"],
                    art.get("summary_ko", ""),
                    art.get("risk_level", "LOW"),
                    art.get("risk_reason", ""),
                    art.get("category", "기타"),
                )

        # ── 6. 감사 (Audit) ───────────────────────────────────
        _update(6, "감사 체크 중", "")
        audit_flags = reviewer.run_audit(run_id, unique_articles)

        # ── 7. 리포트용 기사 조회 ──────────────────────────────
        report_articles = db.get_articles_for_run(run_id)
        if not report_articles:
            report_articles = db.get_articles_in_window(hours_back=config.COLLECT_HOURS_BACK)
        if not report_articles:
            report_articles = summarized

        # ── 8. 리포트 생성 ────────────────────────────────────
        _update(7, "리포트 생성 중", "")
        html_path = html_reporter.generate(report_articles, run_label, audit_flags, run_id)
        md_text, md_path = markdown_reporter.generate(report_articles, run_label, audit_flags)

        # ── 9. 알림 발송 ──────────────────────────────────────
        subject = f"[미디어 리포트] {config.COMPANY_NAME} {run_label} - {datetime.now(KST).strftime('%Y-%m-%d')}"
        slack_notifier.send_report(report_articles, run_label, audit_flags, html_path)
        email_notifier.send_report(subject, md_text, html_path)

        db.mark_included_in_report([a["id"] for a in report_articles if "id" in a])

        # ── 10. 일간 모니터링 로그 누적 기록 ─────────────────────
        db.upsert_daily_log(
            articles=report_articles,
            audit_flags=audit_flags,
            run_count_delta=1,
        )

        # ── 11. 런 완료 기록 ──────────────────────────────────
        db.complete_run(
            run_id=run_id,
            article_count=len(report_articles),
            new_article_count=new_count,
            audit_flags=audit_flags,
            html_path=html_path,
            md_path=md_path,
        )

        if _has_status:
            status["last_result"] = {"collected": len(all_articles), "new": new_count, "error": None}
        logger.info("=== 파이프라인 완료: %s [%d건] ===", run_label, len(report_articles))

    except Exception as e:
        logger.exception("[Pipeline] 파이프라인 오류: %s", e)
        if _has_status:
            status["last_result"] = {"collected": 0, "new": 0, "error": str(e)}
        db.complete_run(run_id, 0, 0, [{"type": "PIPELINE_ERROR", "detail": str(e), "severity": "ERROR"}])
        raise


def job_03():
    run_full_pipeline("03시 정기")


def job_09():
    run_full_pipeline("09시 정기")


def job_15():
    run_full_pipeline("15시 정기")
