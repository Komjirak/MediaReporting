#!/usr/bin/env python3
"""
MediaReporting 메인 엔트리포인트
- 정기 스케줄 (03시 / 09시 / 15시 KST)
- 실시간 모니터링 (스케줄 외 5분 간격)

사용법:
  python main.py                   # 프로덕션 실행 (스케줄 + 모니터)
  python main.py --run now         # 즉시 전체 파이프라인 실행
  python main.py --monitor-only    # 모니터 루프만 실행 (테스트)
  python main.py --run audit       # 감사 리포트만 실행
"""
import argparse
import logging
import logging.handlers
import signal
import sys
import time

import config

# ── 로깅 설정 ─────────────────────────────────────────────────
def _setup_logging():
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # 파일 핸들러 (로테이팅)
    file_handler = logging.handlers.RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)


logger = logging.getLogger(__name__)


def _cmd_search(query: str):
    """일간 로그 전문 검색 결과 출력"""
    from storage import database as db
    results = db.search_daily_logs(query)
    if not results:
        print(f"검색 결과 없음: '{query}'")
        return
    print(f"\n[ 검색: '{query}' | {len(results)}건 ]\n" + "="*60)
    for r in results:
        flags = r.get("audit_flags") or []
        flag_str = f" ⚠️ 감사{len(flags)}건" if flags else ""
        print(
            f"📅 {r['log_date']}  총:{r['total_articles']}건  "
            f"🔴{r['critical_count']} 🟠{r['high_count']} 🟡{r['medium_count']} 🟢{r['low_count']}"
            f"{flag_str}"
        )
        top = r.get("top_articles") or []
        for art in top[:3]:
            print(f"   [{art.get('risk_level','?')}] {art.get('title','')[:60]}")
        if r.get("notes"):
            print(f"   📝 메모: {r['notes']}")
        print()


def _cmd_log(date_str: str):
    """특정 날짜 일간 로그 상세 출력"""
    from storage import database as db
    r = db.get_daily_log(date_str)
    if not r:
        print(f"해당 날짜 기록 없음: {date_str}")
        return
    print(f"\n{'='*60}")
    print(f"📅 {r['log_date']} 일간 모니터링 리포트")
    print(f"{'='*60}")
    print(f"총 기사: {r['total_articles']}건  |  실행: {r['run_count']}회")
    print(f"🔴 CRITICAL: {r['critical_count']}  🟠 HIGH: {r['high_count']}  "
          f"🟡 MEDIUM: {r['medium_count']}  🟢 LOW: {r['low_count']}")

    top = r.get("top_articles") or []
    if top:
        print(f"\n⚡ 주요 기사 (CRITICAL/HIGH):")
        for art in top:
            print(f"  [{art.get('risk_level','?')}] {art.get('title','')}")
            print(f"      {art.get('url','')}")
            if art.get("summary_ko"):
                print(f"      → {art['summary_ko'][:100]}")

    flags = r.get("audit_flags") or []
    if flags:
        print(f"\n⚠️ 감사 플래그 ({len(flags)}건):")
        for f in flags:
            icon = "⛔" if f.get("severity") == "ERROR" else "⚠️"
            ftype = f.get("flag_type") or f.get("type", "")
            fdetail = f.get("flag_detail") or f.get("detail", "")
            print(f"  {icon} [{ftype}] {fdetail}")

    kw = r.get("keywords_coverage") or {}
    if kw:
        print(f"\n📊 키워드 커버리지:")
        for keyword, sources in kw.items():
            n = sources.get("Naver News", 0)
            g = sources.get("Google News", 0)
            print(f"  {keyword}: Naver {n}건 / Google {g}건")

    if r.get("notes"):
        print(f"\n📝 메모:\n{r['notes']}")
    print()


def _run_now():
    """즉시 전체 파이프라인 실행"""
    from scheduler.jobs import run_full_pipeline
    run_full_pipeline("즉시 실행")


def _run_audit():
    """감사 체크만 실행하고 결과 출력"""
    from storage import database as db
    from audit import reviewer
    db.init_db()
    print(reviewer.build_coverage_matrix(hours_back=24))
    print("\n최근 런 통계:")
    for run in db.get_recent_run_stats(hours=48):
        print(f"  [{run['run_type']}] {run['started_at']} - {run['article_count']}건")


def _start_scheduler():
    """APScheduler로 3개 정기 잡 등록 (KST 기준)"""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.error("APScheduler 미설치: pip install apscheduler")
        sys.exit(1)

    from scheduler.jobs import job_03, job_09, job_15

    scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    scheduler.add_job(job_03, CronTrigger(hour=3,  minute=0, timezone="Asia/Seoul"), id="job_03")
    scheduler.add_job(job_09, CronTrigger(hour=9,  minute=0, timezone="Asia/Seoul"), id="job_09")
    scheduler.add_job(job_15, CronTrigger(hour=15, minute=0, timezone="Asia/Seoul"), id="job_15")
    scheduler.start()

    logger.info("스케줄러 시작 - 03:00 / 09:00 / 15:00 KST 정기 실행")
    return scheduler


def _monitor_loop():
    """실시간 모니터링 루프 (블로킹)"""
    from monitor.realtime_monitor import run_monitor_cycle

    interval = config.MONITOR_INTERVAL_SECONDS
    logger.info("실시간 모니터 시작 - 간격: %d초", interval)

    while True:
        try:
            run_monitor_cycle()
        except Exception as e:
            logger.error("[Monitor] 사이클 오류: %s", e)
        time.sleep(interval)


def _handle_signal(sig, frame):
    logger.info("종료 신호 수신 (%s). 시스템 종료 중...", sig)
    sys.exit(0)


def main():
    _setup_logging()

    parser = argparse.ArgumentParser(description="MediaReporting 자동화 시스템")
    parser.add_argument("--run",          help="즉시 실행 모드: now | audit")
    parser.add_argument("--monitor-only", action="store_true", help="모니터 루프만 실행")
    parser.add_argument("--search",       help="일간 로그 검색 (예: --search 소송)")
    parser.add_argument("--log",          help="특정 날짜 일간 로그 조회 (예: --log 2026-04-09)")
    parser.add_argument("--note",         nargs=2, metavar=("DATE", "NOTE"),
                        help="일간 로그 메모 추가 (예: --note 2026-04-09 '대응 완료')")
    args = parser.parse_args()

    # DB 초기화 (항상)
    from storage import database as db
    db.init_db()

    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    if args.search:
        _cmd_search(args.search)
        return

    if args.log:
        _cmd_log(args.log)
        return

    if args.note:
        db.add_daily_note(args.note[0], args.note[1])
        print(f"메모 추가 완료: {args.note[0]} → {args.note[1]}")
        return

    if args.run == "now":
        logger.info("=== 즉시 실행 모드 ===")
        _run_now()
        return

    if args.run == "audit":
        logger.info("=== 감사 리포트 모드 ===")
        _run_audit()
        return

    if args.monitor_only:
        logger.info("=== 모니터 전용 모드 ===")
        _monitor_loop()
        return

    # 기본: 스케줄러 + 모니터 동시 실행
    logger.info("=== MediaReporting 시작 ===")
    logger.info("회사: %s | 키워드: %s", config.COMPANY_NAME, ", ".join(config.KEYWORDS))

    scheduler = _start_scheduler()
    try:
        _monitor_loop()  # 블로킹
    finally:
        scheduler.shutdown(wait=False)
        logger.info("스케줄러 종료 완료")


if __name__ == "__main__":
    main()
