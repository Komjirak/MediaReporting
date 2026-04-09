"""실시간 모니터 - 스케줄 외 시간에 신규 기사 감지 및 즉시 알림"""
import logging
from datetime import datetime, timezone, timedelta

from collectors import google_news, naver_news
from processors import classifier, deduplicator
from storage import database as db
from notifiers import email_notifier, slack_notifier
import config

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _format_alert_body(article: dict) -> str:
    pub = article.get("published_at", "")[:16].replace("T", " ")
    return (
        f"[{article.get('risk_level','?')} 알림] {config.COMPANY_NAME} 신규 기사\n\n"
        f"제목: {article['title']}\n"
        f"링크: {article['url']}\n"
        f"소스: {article['source']} | 발행: {pub}\n"
        f"리스크: {article.get('risk_reason', '-')}\n\n"
        f"{article.get('description', '')[:300]}"
    )


def run_monitor_cycle():
    """
    모니터 1회 실행 사이클:
    1. 수집 (최근 1시간 기사만 - 빠른 갱신 감지)
    2. URL 해시 중복 제거만 (제목 유사도 X - 속도 우선)
    3. 키워드 기반 리스크 분류 (Claude 미사용 - 비용 절감)
    4. DB 저장
    5. CRITICAL/HIGH는 즉시 알림 발송
    """
    logger.debug("[Monitor] 수집 사이클 시작")

    # 1. 수집 (최근 1시간)
    google_articles = google_news.collect(hours_back=1)
    naver_articles = naver_news.collect(hours_back=1)
    all_articles = google_articles + naver_articles

    if not all_articles:
        logger.debug("[Monitor] 신규 기사 없음")
        return

    # 2. URL 해시 중복 제거 (배치 내 제목 유사도 체크 생략)
    new_articles = []
    for art in all_articles:
        if not db.is_duplicate(art["url"]):
            art["title_normalized"] = art["title"].lower()
            new_articles.append(art)

    if not new_articles:
        logger.debug("[Monitor] 모두 중복 기사 - 신규 없음")
        return

    logger.info("[Monitor] 신규 기사 %d건 감지", len(new_articles))

    # 3. 리스크 분류 (키워드 기반)
    for art in new_articles:
        art["risk_level"], art["risk_reason"] = classifier.classify_risk(art)
        art["category"] = classifier.classify_category(art)

    # 4. DB 저장 (run_id는 "monitor" 고정)
    for art in new_articles:
        db.insert_article(art, run_id="monitor")

    # 5. CRITICAL/HIGH 즉시 알림
    high_risk = [a for a in new_articles if a["risk_level"] in ("CRITICAL", "HIGH")]
    if high_risk:
        logger.warning("[Monitor] %d건 고위험 기사 즉시 알림 발송", len(high_risk))
        for art in high_risk:
            # Slack 알림
            slack_notifier.send_alert(art, reason=art.get("risk_reason", ""))
            # 이메일 알림
            subject = f"[{art['risk_level']}] {config.COMPANY_NAME} 기사 알림: {art['title'][:50]}"
            email_notifier.send_alert(subject, _format_alert_body(art))

        # notified 플래그 업데이트
        ids = [a["id"] for a in high_risk if "id" in a]
        # DB에서 방금 저장된 기사의 id를 가져옴
        unnotified = db.get_unnotified_high_risk()
        notified_ids = [u["id"] for u in unnotified
                        if u["url"] in {a["url"] for a in high_risk}]
        db.mark_notified(notified_ids)
