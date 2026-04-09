"""SMTP 이메일 발송 모듈"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

import config

logger = logging.getLogger(__name__)


def _build_smtp():
    smtp = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20)
    smtp.ehlo()
    smtp.starttls()
    smtp.login(config.SMTP_USER, config.SMTP_PASS)
    return smtp


def send_report(subject: str, body_md: str, html_path: str = ""):
    """정기 리포트 발송 - Markdown 본문 + HTML 첨부"""
    if not config.EMAIL_RECIPIENTS or not config.SMTP_USER:
        logger.warning("[Email] 설정 미완료. 이메일 발송 건너뜀.")
        return

    msg = MIMEMultipart("mixed")
    msg["From"] = config.SMTP_USER
    msg["To"] = ", ".join(config.EMAIL_RECIPIENTS)
    msg["Subject"] = subject

    msg.attach(MIMEText(body_md, "plain", "utf-8"))

    # HTML 파일 첨부
    if html_path and Path(html_path).exists():
        with open(html_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{Path(html_path).name}"',
        )
        msg.attach(part)

    _send(msg)


def send_alert(subject: str, body: str):
    """실시간 알림 발송 (단문)"""
    if not config.EMAIL_RECIPIENTS or not config.SMTP_USER:
        logger.warning("[Email] 설정 미완료. 알림 발송 건너뜀.")
        return

    msg = MIMEMultipart()
    msg["From"] = config.SMTP_USER
    msg["To"] = ", ".join(config.EMAIL_RECIPIENTS)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    _send(msg)


def _send(msg: MIMEMultipart):
    try:
        with _build_smtp() as smtp:
            smtp.sendmail(config.SMTP_USER, config.EMAIL_RECIPIENTS, msg.as_string())
        logger.info("[Email] 발송 완료: %s", msg["Subject"])
    except Exception as e:
        logger.error("[Email] 발송 실패: %s", e)
