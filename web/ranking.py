"""기사 랭킹 스코어링 - 정확도 기반"""
from datetime import datetime, timezone, timedelta
import config

KST = timezone(timedelta(hours=9))

_RISK_SCORE = {"CRITICAL": 100, "HIGH": 75, "MEDIUM": 45, "LOW": 10}


def _keyword_score(article: dict) -> tuple[int, bool]:
    """회사명/주요 키워드 직접 매칭 강도. (점수, 회사명직접포함여부) 반환"""
    text = " ".join([
        article.get("title", ""),
        article.get("summary_ko", ""),
        article.get("description", ""),
    ]).lower()

    company = config.COMPANY_NAME.lower()
    score = 0
    has_company = company in text

    # 회사명 직접 포함
    if has_company:
        score += 50

    # 키워드별 가중치 (첫 번째 키워드일수록 중요)
    for i, kw in enumerate(config.KEYWORDS):
        if kw.lower() in text:
            weight = max(40 - i * 5, 10)  # 1번 키워드 40점, 이후 5점씩 감소
            score += weight
            break  # 가장 높은 키워드 점수만 적용

    return min(score, 80), has_company  # 최대 80점


def _recency_score(article: dict) -> int:
    """최신성 점수 (6시간 이내 = 20점, 24시간 이내 = 10점, 그 이상 = 0점)"""
    pub_str = article.get("published_at", "")
    if not pub_str:
        return 0
    try:
        pub = datetime.fromisoformat(pub_str)
        hours_ago = (datetime.now(KST) - pub).total_seconds() / 3600
        if hours_ago <= 6:
            return 20
        elif hours_ago <= 24:
            return 10
        return 0
    except Exception:
        return 0


def _source_score(article: dict) -> int:
    """Naver News 우선 (국내 소스)"""
    return 5 if article.get("source") == "Naver News" else 0


def _summary_score(article: dict) -> int:
    """요약 있으면 가산점"""
    return 5 if article.get("summary_ko") else 0


def rank_articles(articles: list[dict]) -> list[dict]:
    """
    기사 목록에 랭킹 점수를 부여하고 내림차순 정렬.
    점수 구성: 리스크(관련성 보정) + 키워드 매칭(80) + 최신성(20) + 소스(5) + 요약(5)

    관련성 보정: 회사명/키워드가 본문에 없으면 리스크 점수를 대폭 감소시켜
    무관한 기사가 CRITICAL 점수만으로 상위에 오르는 것을 방지.
    """
    for art in articles:
        kw_score, has_company = _keyword_score(art)
        risk = _RISK_SCORE.get(art.get("risk_level", "LOW"), 10)

        # 관련성 보정: 키워드 매칭 강도에 따라 리스크 점수 조정
        if has_company:
            pass  # 회사명 직접 포함 → 리스크 점수 전액 반영
        elif kw_score >= 30:
            risk = int(risk * 0.6)  # 약한 키워드 매칭 → 60%만 반영
        elif kw_score > 0:
            risk = int(risk * 0.3)  # 아주 약한 매칭 → 30%만 반영
        else:
            risk = int(risk * 0.1)  # 키워드 전혀 없음 → 10%만 반영

        score = (
            risk
            + kw_score
            + _recency_score(art)
            + _source_score(art)
            + _summary_score(art)
        )
        art["_score"] = score

    return sorted(articles, key=lambda a: a["_score"], reverse=True)
