"""중복 제거 - URL 해시 + 제목 유사도 기반"""
import re
import logging
from storage import database as db
import config

logger = logging.getLogger(__name__)


def _normalize_title(title: str) -> str:
    """제목 정규화: 소문자, 특수문자/공백 제거"""
    title = title.lower()
    title = re.sub(r"[^\w가-힣]", "", title)
    return title


def _ngram_jaccard(a: str, b: str, n: int = 2) -> float:
    """문자 n-gram Jaccard 유사도"""
    if not a or not b:
        return 0.0
    set_a = set(a[i:i+n] for i in range(len(a) - n + 1))
    set_b = set(b[i:i+n] for i in range(len(b) - n + 1))
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def deduplicate(articles: list[dict]) -> list[dict]:
    """
    1단계: DB 기반 URL 해시 중복 제거 (이미 수집된 기사)
    2단계: 현재 배치 내 제목 유사도 중복 제거 (같은 기사가 다른 소스로 중복 수집)
    Naver News 우선 (한국어 소스)
    """
    # 1단계: DB 중복 제거
    new_articles = []
    for art in articles:
        if db.is_duplicate(art["url"]):
            logger.debug("[Dedup] URL 중복 제거: %s", art["title"][:40])
            continue
        art["title_normalized"] = _normalize_title(art["title"])
        new_articles.append(art)

    # 2단계: 배치 내 제목 유사도 중복 제거
    # Naver News를 우선 유지하기 위해 Naver를 먼저 처리
    naver = [a for a in new_articles if a["source"] == "Naver News"]
    others = [a for a in new_articles if a["source"] != "Naver News"]

    kept: list[dict] = list(naver)  # Naver는 전부 유지

    for art in others:
        is_dup = False
        for kept_art in kept:
            sim = _ngram_jaccard(art["title_normalized"], kept_art["title_normalized"])
            if sim >= config.DEDUP_TITLE_SIMILARITY_THRESHOLD:
                logger.debug(
                    "[Dedup] 제목 유사도 %.2f → 제거: %s", sim, art["title"][:40]
                )
                is_dup = True
                break
        if not is_dup:
            kept.append(art)

    removed = len(articles) - len(kept)
    logger.info("[Dedup] %d건 중 %d건 중복 제거 → %d건 남음", len(articles), removed, len(kept))
    return kept
