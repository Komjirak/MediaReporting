"""Markdown 리포트 생성 (Slack/이메일 텍스트 용도)"""
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import config

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

_RISK_EMOJI = {
    "CRITICAL": "🔴",
    "HIGH":     "🟠",
    "MEDIUM":   "🟡",
    "LOW":      "🟢",
}


def generate(articles: list[dict], run_label: str,
             audit_flags: list[dict]) -> tuple[str, str]:
    """
    Markdown 리포트 생성.
    반환: (markdown_text, file_path)
    """
    now_kst = datetime.now(KST)
    run_time = now_kst.strftime("%Y-%m-%d %H:%M")
    filename = now_kst.strftime("%Y-%m-%d_%H%M") + "_KST.md"
    output_path = config.REPORTS_MD_DIR / filename

    risk_counts = {}
    for level in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        risk_counts[level] = sum(1 for a in articles if a.get("risk_level") == level)

    lines = [
        f"# {config.COMPANY_NAME} 미디어 리포트 - {run_label}",
        f"**생성:** {run_time} KST  |  **수집 기간:** 최근 {config.COLLECT_HOURS_BACK}시간  |  **총:** {len(articles)}건",
        "",
        "## 리스크 요약",
        f"🔴 CRITICAL: {risk_counts['CRITICAL']}건  |  "
        f"🟠 HIGH: {risk_counts['HIGH']}건  |  "
        f"🟡 MEDIUM: {risk_counts['MEDIUM']}건  |  "
        f"🟢 LOW: {risk_counts['LOW']}건",
        "",
    ]

    # 감사 경고
    if audit_flags:
        lines.append("## ⚠️ 감사 알림")
        for f in audit_flags:
            icon = "⛔" if f["severity"] == "ERROR" else "⚠️"
            flag_type = f.get("flag_type") or f.get("type", "")
            flag_detail = f.get("flag_detail") or f.get("detail", "")
            lines.append(f"- {icon} **[{flag_type}]** {flag_detail}")
        lines.append("")

    # 기사 목록
    lines.append("## 기사 목록")
    if not articles:
        lines.append("_해당 기간 수집된 기사가 없습니다._")
    else:
        for art in articles:
            emoji = _RISK_EMOJI.get(art.get("risk_level", "LOW"), "🟢")
            pub = art.get("published_at", "")[:16].replace("T", " ")
            lines.append(f"\n### {emoji} [{art.get('risk_level','LOW')}] {art['title']}")
            lines.append(f"**링크:** {art['url']}")
            lines.append(f"**소스:** {art['source']}  |  **발행:** {pub}  |  **카테고리:** {art.get('category','-')}  |  **키워드:** {art.get('keyword','-')}")
            if art.get("summary_ko"):
                lines.append(f"\n> {art['summary_ko']}")
            elif art.get("description"):
                lines.append(f"\n> {art['description'][:200]}")
            if art.get("risk_reason"):
                lines.append(f"\n*리스크 사유: {art['risk_reason']}*")

    lines.append("")
    lines.append("---")
    lines.append(f"*MediaReporting System | {run_time} KST*")

    md_text = "\n".join(lines)
    output_path.write_text(md_text, encoding="utf-8")
    logger.info("[MD Reporter] 리포트 저장: %s (%d건)", output_path, len(articles))
    return md_text, str(output_path)
