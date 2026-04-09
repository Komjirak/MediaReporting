"""감사/리뷰 로직 - 누락 기사 없는지 5가지 체크"""
import logging
from datetime import datetime, timezone, timedelta
from storage import database as db
import config

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    return datetime.now(KST)


def run_audit(run_id: str, new_articles: list[dict]) -> list[dict]:
    """
    수집 완료 후 5가지 감사 체크 실행.
    문제 발견 시 audit_log에 기록하고 플래그 목록 반환.
    """
    flags = []

    flags.extend(_check_low_count(run_id, new_articles))
    flags.extend(_check_keyword_gap(run_id))
    flags.extend(_check_source_failure(run_id, new_articles))
    flags.extend(_check_duplicate_surge(run_id, new_articles))
    flags.extend(_check_unresolved_critical(run_id))

    for flag in flags:
        db.insert_audit_flag(
            run_id=run_id,
            flag_type=flag["type"],
            flag_detail=flag["detail"],
            severity=flag["severity"],
        )
        level = logging.ERROR if flag["severity"] == "ERROR" else logging.WARNING
        logger.log(level, "[Audit] %s: %s", flag["type"], flag["detail"])

    if not flags:
        logger.info("[Audit] run_id=%s: 모든 감사 통과", run_id)

    return flags


def _check_low_count(run_id: str, new_articles: list[dict]) -> list[dict]:
    """수집 건수가 너무 적으면 경고"""
    flags = []
    if len(new_articles) < config.AUDIT_MIN_ARTICLES:
        flags.append({
            "type":     "LOW_COUNT",
            "detail":   f"수집 기사 {len(new_articles)}건 (기준: {config.AUDIT_MIN_ARTICLES}건 이상)",
            "severity": "WARNING",
        })
    return flags


def _check_keyword_gap(run_id: str) -> list[dict]:
    """지난 24시간 동안 특정 키워드에서 기사가 한 건도 없으면 경고"""
    flags = []
    kw_counts = db.get_keyword_counts_by_source(hours_back=24)
    for keyword in config.KEYWORDS:
        if keyword not in kw_counts:
            flags.append({
                "type":     "KEYWORD_GAP",
                "detail":   f"키워드 '{keyword}' 최근 24시간 기사 0건 - 수집 이상 또는 실제 무소식",
                "severity": "WARNING",
            })
    return flags


def _check_source_failure(run_id: str, new_articles: list[dict]) -> list[dict]:
    """특정 소스에서 한 건도 수집되지 않으면 경고.
    단, 중복 제거 후 0건인 경우(이전에 수집된 적 있음)는 제외."""
    flags = []
    # 중복 제거 후 0건인 경우 - DB에 기사가 있으면 정상 (수집 자체는 됐음)
    if not new_articles:
        # 최근 6시간 DB 기사 확인
        recent = db.get_articles_in_window(hours_back=config.COLLECT_HOURS_BACK)
        if recent:
            return []  # DB에 기사 있으면 수집 실패 아님

    sources_collected = {a["source"] for a in new_articles}
    for expected_source in ["Google News", "Naver News"]:
        if expected_source not in sources_collected:
            flags.append({
                "type":     "SOURCE_FAILURE",
                "detail":   f"{expected_source} 수집 결과 0건 - API/네트워크 이상 가능성",
                "severity": "ERROR",
            })
    return flags


def _check_duplicate_surge(run_id: str, new_articles: list[dict]) -> list[dict]:
    """중복 제거율이 비정상적으로 높으면 경고 (캐시된 오래된 콘텐츠 가능성)"""
    flags = []
    # 실제 중복율은 collect 단계에서 측정하기 어려우므로,
    # DB에서 최근 1시간 내 동일 URL 중복 삽입 시도를 간접 측정
    recent_runs = db.get_recent_run_stats(hours=2)
    if len(recent_runs) >= 2:
        last_run = recent_runs[0]
        # 이전 런과 비교해 신규 기사가 0건인 경우
        if (last_run.get("new_article_count", 1) == 0
                and last_run.get("article_count", 0) > 0):
            flags.append({
                "type":     "DUPLICATE_SURGE",
                "detail":   "직전 런 대비 신규 기사 0건 - 중복 급증 또는 수집 정체 가능성",
                "severity": "WARNING",
            })
    return flags


def _check_unresolved_critical(run_id: str) -> list[dict]:
    """CRITICAL/HIGH 기사 중 아직 알림 미발송된 것이 있으면 에러"""
    flags = []
    unnotified = db.get_unnotified_high_risk()
    # 6시간 이상 된 미알림 CRITICAL/HIGH 기사
    cutoff = (datetime.now(KST) - timedelta(hours=6)).isoformat()
    old_unnotified = [
        a for a in unnotified
        if a["collected_at"] < cutoff and a["risk_level"] == "CRITICAL"
    ]
    if old_unnotified:
        titles = ", ".join(a["title"][:30] for a in old_unnotified[:3])
        flags.append({
            "type":     "UNRESOLVED_CRITICAL",
            "detail":   f"6시간 이상 알림 미발송 CRITICAL 기사 {len(old_unnotified)}건: {titles}...",
            "severity": "ERROR",
        })
    return flags


def build_coverage_matrix(hours_back: int = 24) -> str:
    """키워드×소스 커버리지 매트릭스 텍스트 생성"""
    kw_counts = db.get_keyword_counts_by_source(hours_back=hours_back)
    sources = ["Naver News", "Google News"]
    lines = ["| 키워드 | Naver | Google |", "|--------|-------|--------|"]
    for kw in config.KEYWORDS:
        n = kw_counts.get(kw, {}).get("Naver News", 0)
        g = kw_counts.get(kw, {}).get("Google News", 0)
        lines.append(f"| {kw} | {n} | {g} |")
    return "\n".join(lines)
