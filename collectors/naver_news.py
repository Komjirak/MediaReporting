"""Naver 뉴스 검색 API 수집기"""
import logging
import re
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _strip_bold(text: str) -> str:
    """Naver API 결과의 <b>, </b> 태그 제거"""
    return re.sub(r"</?b>", "", text or "").strip()


def _parse_naver_date(date_str: str) -> str:
    """RFC2822 날짜 → KST ISO 문자열"""
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(KST).isoformat()
    except Exception:
        return datetime.now(KST).isoformat()


def _fetch_naver(keyword: str, display: int = 50, start: int = 1) -> list[dict]:
    if not config.NAVER_CLIENT_ID or not config.NAVER_CLIENT_SECRET:
        logger.warning("[Naver] API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")
        return []

    headers = {
        "X-Naver-Client-Id":     config.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET,
    }
    params = {
        "query":   keyword,
        "display": display,
        "start":   start,
        "sort":    "date",
    }
    try:
        resp = requests.get(
            config.NAVER_NEWS_API_URL,
            headers=headers,
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("items", [])
    except requests.HTTPError as e:
        logger.error("[Naver] HTTP 오류 (%s): %s", keyword, e)
        return []
    except Exception as e:
        logger.error("[Naver] 수집 오류 (%s): %s", keyword, e)
        return []


def collect(keywords: Optional[list[str]] = None, hours_back: int = None) -> list[dict]:
    """
    Naver 뉴스 API에서 키워드별 기사 수집.
    hours_back: 최근 N시간 이내 기사만 반환
    """
    keywords = keywords or config.KEYWORDS
    hours_back = hours_back or config.COLLECT_HOURS_BACK
    cutoff = datetime.now(KST) - timedelta(hours=hours_back)

    articles = []
    for keyword in keywords:
        items = _fetch_naver(keyword, display=config.NAVER_DISPLAY)
        count = 0
        for item in items:
            published_str = _parse_naver_date(item.get("pubDate", ""))
            published_dt = datetime.fromisoformat(published_str)
            if published_dt < cutoff.astimezone(KST):
                continue

            title = _strip_bold(item.get("title", ""))
            description = _strip_bold(item.get("description", ""))
            url = item.get("originallink") or item.get("link", "")

            articles.append({
                "title":       title,
                "url":         url,
                "source":      "Naver News",
                "keyword":     keyword,
                "published_at": published_str,
                "collected_at": datetime.now(KST).isoformat(),
                "description": description,
            })
            count += 1

        logger.info("[Naver] '%s' → %d건 수집", keyword, count)
        time.sleep(0.5)  # 레이트 리밋

    logger.info("[Naver] 전체 %d건 수집 완료", len(articles))
    return articles
