"""Slack Incoming Webhook 발송 모듈 (Block Kit)"""
import json
import logging
import urllib.request
import urllib.error

import config

logger = logging.getLogger(__name__)

_RISK_COLOR = {
    "CRITICAL": "#e53e3e",
    "HIGH":     "#dd6b20",
    "MEDIUM":   "#d69e2e",
    "LOW":      "#38a169",
}
_RISK_EMOJI = {
    "CRITICAL": "🔴",
    "HIGH":     "🟠",
    "MEDIUM":   "🟡",
    "LOW":      "🟢",
}


def _post(payload: dict):
    if not config.SLACK_WEBHOOK_URL:
        logger.warning("[Slack] Webhook URL 미설정. 발송 건너뜀.")
        return
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            config.SLACK_WEBHOOK_URL,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            logger.info("[Slack] 발송 완료: %s", resp.read().decode())
    except urllib.error.URLError as e:
        logger.error("[Slack] 발송 실패: %s", e)


def send_report(articles: list[dict], run_label: str,
                audit_flags: list[dict], html_path: str = ""):
    """정기 리포트 Slack 발송 (상위 5건 + 리스크 요약)"""
    risk_counts = {lv: sum(1 for a in articles if a.get("risk_level") == lv)
                   for lv in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]}

    header = (
        f"*{config.COMPANY_NAME} 미디어 리포트 - {run_label}*\n"
        f"🔴 {risk_counts['CRITICAL']}건  🟠 {risk_counts['HIGH']}건  "
        f"🟡 {risk_counts['MEDIUM']}건  🟢 {risk_counts['LOW']}건  |  "
        f"총 {len(articles)}건"
    )

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": header}},
        {"type": "divider"},
    ]

    # 감사 경고
    if audit_flags:
        flag_text = "\n".join(
            f"{'⛔' if f.get('severity')=='ERROR' else '⚠️'} [{f.get('flag_type') or f.get('type','')}] {f.get('flag_detail') or f.get('detail','')}"
            for f in audit_flags
        )
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*감사 알림*\n{flag_text}"},
        })
        blocks.append({"type": "divider"})

    # 상위 5건 (CRITICAL/HIGH 우선)
    top_articles = sorted(
        articles,
        key=lambda a: ["CRITICAL","HIGH","MEDIUM","LOW"].index(a.get("risk_level","LOW"))
    )[:5]

    for art in top_articles:
        lvl = art.get("risk_level", "LOW")
        emoji = _RISK_EMOJI[lvl]
        pub = art.get("published_at", "")[:16].replace("T", " ")
        summary = art.get("summary_ko") or art.get("description", "")[:150]

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{emoji} *<{art['url']}|{art['title']}>*\n"
                    f"_{art['source']} | {pub} | {art.get('category','-')}_\n"
                    f"{summary}"
                ),
            },
        })

    if html_path:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"📄 HTML 리포트: `{html_path}`"}],
        })

    _post({"blocks": blocks})


def send_alert(article: dict, reason: str = ""):
    """실시간 CRITICAL/HIGH 기사 알림"""
    lvl = article.get("risk_level", "HIGH")
    color = _RISK_COLOR.get(lvl, "#aaa")
    emoji = _RISK_EMOJI.get(lvl, "🟡")
    pub = article.get("published_at", "")[:16].replace("T", " ")
    summary = article.get("summary_ko") or article.get("description", "")[:200]

    payload = {
        "attachments": [{
            "color": color,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"{emoji} *[{lvl} 알림] {config.COMPANY_NAME} 신규 기사*\n"
                            f"*<{article['url']}|{article['title']}>*\n"
                            f"_{article['source']} | {pub}_"
                        ),
                    },
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": summary or "(요약 없음)"},
                },
            ],
        }]
    }
    if reason:
        payload["attachments"][0]["blocks"].append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"⚠️ {reason}"}],
        })

    _post(payload)
