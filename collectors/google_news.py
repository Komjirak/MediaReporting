"""Google News RSS 수집기"""
import logging
import re
import time
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Optional

import feedparser
import requests

import config

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _resolve_redirect(url: str) -> str:
    """Google 리디렉션 URL 그대로 반환 (클릭 시 자동 리디렉션됨)"""
    return url


def _parse_published(entry) -> str:
    """feedparser published_parsed → KST ISO 문자열"""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        utc_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        return utc_dt.astimezone(KST).isoformat()
    return datetime.now(KST).isoformat()


def collect(keywords: Optional[list[str]] = None, hours_back: int = None) -> list[dict]:
    """
    Google News RSS에서 키워드별 기사 수집.
    hours_back: 최근 N시간 이내 기사만 반환 (None이면 전체)
    """
    keywords = keywords or config.KEYWORDS
    hours_back = hours_back or config.COLLECT_HOURS_BACK
    cutoff = datetime.now(KST) - timedelta(hours=hours_back)

    articles = []
    for keyword in keywords:
        url = config.GOOGLE_NEWS_RSS_TEMPLATE.format(
            query=urllib.parse.quote(keyword)
        )
        try:
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                logger.warning("[Google] 피드 파싱 실패: %s (%s)", keyword, feed.bozo_exception)
                continue

            for entry in feed.entries:
                published_str = _parse_published(entry)
                published_dt = datetime.fromisoformat(published_str)
                if published_dt < cutoff.astimezone(KST):
                    continue  # 수집 기간 외 기사 제외

                raw_url = entry.get("link", "")
                resolved_url = _resolve_redirect(raw_url)

                title = _clean_html(entry.get("title", ""))
                description = _clean_html(entry.get("summary", ""))

                articles.append({
                    "title":      title,
                    "url":        resolved_url,
                    "source":     "Google News",
                    "keyword":    keyword,
                    "published_at": published_str,
                    "collected_at": datetime.now(KST).isoformat(),
                    "description": description,
                })

            logger.info("[Google] '%s' → %d건 수집", keyword, len(feed.entries))
            time.sleep(1)  # 레이트 리밋

        except Exception as e:
            logger.error("[Google] '%s' 수집 오류: %s", keyword, e)

    logger.info("[Google] 전체 %d건 수집 완료", len(articles))
    return articles
