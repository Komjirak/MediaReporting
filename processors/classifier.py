"""키워드 기반 빠른 리스크 분류기 (Claude API 호출 없음)"""
import re
import config


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def classify_risk(article: dict) -> tuple[str, str]:
    """
    기사의 title + description에서 리스크 키워드를 탐지.
    반환: (risk_level, risk_reason)
    risk_level: CRITICAL | HIGH | MEDIUM | LOW
    """
    text = " ".join([
        article.get("title", ""),
        article.get("description", ""),
    ])
    text_norm = _normalize(text)

    for kw in config.RISK_KEYWORDS_CRITICAL:
        if _normalize(kw) in text_norm:
            return "CRITICAL", f"CRITICAL 키워드 감지: {kw}"

    for kw in config.RISK_KEYWORDS_HIGH:
        if _normalize(kw) in text_norm:
            return "HIGH", f"HIGH 키워드 감지: {kw}"

    # MEDIUM: 일반 부정적 표현
    medium_kws = ["논란", "비판", "우려", "하락", "손실", "적자", "감소", "문제", "갈등"]
    for kw in medium_kws:
        if kw in text:
            return "MEDIUM", f"주의 키워드 감지: {kw}"

    return "LOW", ""


def classify_category(article: dict) -> str:
    """제목/설명 기반 카테고리 분류"""
    text = article.get("title", "") + " " + article.get("description", "")

    rules = [
        ("기업 실적", ["실적", "매출", "영업이익", "순이익", "흑자", "적자", "분기", "연간"]),
        ("인사/조직",  ["대표이사", "CEO", "사장", "임원", "인사", "조직개편", "채용", "해고"]),
        ("법률/규제",  ["소송", "수사", "기소", "규제", "법원", "판결", "벌금", "과태료"]),
        ("제품/서비스", ["출시", "신제품", "서비스", "업데이트", "론칭", "개발", "특허"]),
        ("M&A/투자",   ["인수", "합병", "투자", "지분", "펀딩", "상장", "IPO"]),
        ("사회/이슈",  ["사회", "환경", "ESG", "안전", "사고", "논란", "비판"]),
    ]
    for category, keywords in rules:
        if any(kw in text for kw in keywords):
            return category

    return "기타"
