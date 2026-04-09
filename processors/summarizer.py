"""Gemini API 기반 기사 요약 (google.genai 신규 SDK)"""
import json
import logging
import re
import time

import config

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        try:
            import google.genai as genai
            _client = genai.Client(api_key=config.GEMINI_API_KEY)
        except ImportError:
            logger.error("google-genai 미설치: pip install google-genai")
            raise
    return _client


PROMPT_TEMPLATE = """다음 뉴스 기사를 분석하여 반드시 아래 JSON 형식으로만 응답하세요.
JSON 외 다른 텍스트(마크다운 코드블록 포함)는 절대 출력하지 마세요.

제목: {title}
내용: {description}

{{
  "summary_ko": "2~3문장 한국어 요약. 핵심 사실만.",
  "risk_level": "CRITICAL|HIGH|MEDIUM|LOW 중 하나",
  "risk_reason": "판단 근거 (없으면 빈 문자열)",
  "category": "기업 실적|인사/조직|법률/규제|제품/서비스|M&A/투자|사회/이슈|기타 중 하나"
}}

판단 기준:
- CRITICAL: 기소, 구속, 파산, 대형 사고/사망
- HIGH: 소송, 벌금, 리콜, 수사, 대규모 논란
- MEDIUM: 실적 하락, 소규모 논란, 조직 갈등
- LOW: 일반 기업 소식, 신제품, 행사"""


def _extract_json(text: str) -> dict:
    # 1) 코드블록 제거 후 파싱 시도
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # 2) 텍스트 내 { ... } 패턴을 직접 추출
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group())
    raise json.JSONDecodeError("JSON not found", text, 0)


def _summarize_one(article: dict) -> dict:
    title = article.get("title", "")
    description = (article.get("description", "") or "")[:600]
    prompt = PROMPT_TEMPLATE.format(title=title, description=description)

    client = _get_client()
    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config={
                "temperature": 0.1,
                "max_output_tokens": config.SUMMARIZE_MAX_TOKENS,
                "thinking_config": {"thinking_budget": 0},  # thinking 비활성화
            },
        )
        raw = response.text.strip()
        result = _extract_json(raw)
        return {
            "summary_ko":  result.get("summary_ko", ""),
            "risk_level":  result.get("risk_level", article.get("risk_level", "LOW")),
            "risk_reason": result.get("risk_reason", ""),
            "category":    result.get("category", "기타"),
        }
    except json.JSONDecodeError:
        logger.warning("[Summarizer] JSON 파싱 실패: %s | raw: %s", title[:40], (raw if 'raw' in dir() else '')[:100])
        return {
            "summary_ko":  "",
            "risk_level":  article.get("risk_level", "LOW"),
            "risk_reason": article.get("risk_reason", ""),
            "category":    article.get("category", "기타"),
        }
    except Exception as e:
        logger.error("[Summarizer] Gemini 오류 (%s): %s", title[:40], e)
        return {
            "summary_ko":  "",
            "risk_level":  article.get("risk_level", "LOW"),
            "risk_reason": article.get("risk_reason", ""),
            "category":    article.get("category", "기타"),
        }


def summarize_batch(articles: list[dict], batch_size: int = 10) -> list[dict]:
    if not config.GEMINI_API_KEY:
        logger.warning("[Summarizer] GEMINI_API_KEY 미설정. 요약 건너뜀.")
        return articles

    results = []
    for i in range(0, len(articles), batch_size):
        batch = articles[i:i + batch_size]
        for art in batch:
            summary_data = _summarize_one(art)
            art.update(summary_data)
            results.append(art)
        if i + batch_size < len(articles):
            time.sleep(1)

    logger.info("[Summarizer] %d건 Gemini 요약 완료", len(results))
    return results
