"""Jinja2 기반 HTML 리포트 생성"""
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from audit import reviewer
import config

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)


def generate(articles: list[dict], run_label: str, audit_flags: list[dict],
             run_id: str) -> str:
    """
    HTML 리포트 생성 후 파일 경로 반환.
    articles: 이미 요약/분류된 기사 목록
    """
    now_kst = datetime.now(KST)
    run_time = now_kst.strftime("%Y-%m-%d %H:%M")
    filename = now_kst.strftime("%Y-%m-%d_%H%M") + "_KST.html"
    output_path = config.REPORTS_HTML_DIR / filename

    coverage_matrix = reviewer.build_coverage_matrix(hours_back=24)

    template = _jinja_env.get_template("report.html.j2")
    html = template.render(
        company_name=config.COMPANY_NAME,
        run_label=run_label,
        run_time=run_time,
        hours_back=config.COLLECT_HOURS_BACK,
        articles=articles,
        audit_flags=audit_flags,
        coverage_matrix=coverage_matrix,
    )

    output_path.write_text(html, encoding="utf-8")
    logger.info("[HTML Reporter] 리포트 저장: %s (%d건)", output_path, len(articles))
    return str(output_path)
