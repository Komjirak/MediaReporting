# MediaReporting 설치/운영 가이드 (read.md)

이 문서는 다른 개발자/운영자가 프로젝트를 그대로 가져와 실행하고 확장할 수 있도록 구성한 실행 가이드다.

## 1. 준비 사항
- OS: macOS/Linux/WSL 권장
- Python: 3.10+
- 패키지 관리자: `pip`
- (선택) 배포: Vercel CLI (`npm i -g vercel`)

## 2. 프로젝트 설치
```bash
# 1) 프로젝트 경로 이동
cd MediaReporting

# 2) 가상환경 생성/활성화
python3 -m venv .venv
source .venv/bin/activate

# 3) 의존성 설치
pip install -r requirements.txt
```

## 3. 개인 설정(.env)
```bash
cp .env.example .env
```

다음 값을 반드시 본인 계정으로 채워야 한다.

### 3.1 필수 설정
- `COMPANY_NAME`: 모니터링할 회사명
- `KEYWORDS`: 검색 키워드(쉼표 구분)

### 3.2 뉴스 수집 API
- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`
- `GEMINI_API_KEY` (요약 기능)

권장: Naver/Gemini 모두 설정. 둘 중 일부가 없으면 수집/요약 품질이 저하될 수 있다.

### 3.3 알림 채널 설정
- Slack
  - `SLACK_WEBHOOK_URL`: Incoming Webhook URL
- Email (SMTP)
  - `SMTP_HOST`, `SMTP_PORT`
  - `SMTP_USER`, `SMTP_PASS`
  - `EMAIL_RECIPIENTS` (쉼표 구분)

둘 중 하나만 설정해도 동작하지만, 운영에서는 Slack + Email 동시 설정을 권장한다.

### 3.4 운영 튜닝 설정
- `MONITOR_INTERVAL_SECONDS`: 실시간 모니터 주기(초)
- `AUDIT_MIN_ARTICLES`: 감사 최소 기사 기준

## 4. 실행 방법

### 4.1 기본 운영 실행 (스케줄 + 실시간 모니터)
```bash
python main.py
```

### 4.2 즉시 1회 전체 파이프라인 실행
```bash
python main.py --run now
```

### 4.3 감사 리포트만 실행
```bash
python main.py --run audit
```

### 4.4 모니터 루프만 실행
```bash
python main.py --monitor-only
```

### 4.5 일간 로그 조회/검색
```bash
python main.py --log 2026-04-09
python main.py --search 소송
python main.py --note 2026-04-09 "대응 완료"
```

## 5. 웹 대시보드 실행
```bash
python web/app.py
```
기본 포트: `5100`
브라우저: `http://localhost:5100`

## 6. Vercel 배포
이 프로젝트는 Flask 웹을 Vercel 서버리스로 배포하도록 구성됨.

### 6.1 최초 배포
```bash
vercel --prod
```

### 6.2 배포 후 환경변수 등록
Vercel 프로젝트 환경변수에 `.env`의 핵심 값 등록:
- `COMPANY_NAME`, `KEYWORDS`
- `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`
- `GEMINI_API_KEY`
- `SLACK_WEBHOOK_URL`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_RECIPIENTS`
- `MONITOR_INTERVAL_SECONDS`, `AUDIT_MIN_ARTICLES`

등록 후 재배포:
```bash
vercel --prod
```

## 7. 출력물/데이터 위치
- DB: `data/articles.db`
- 로그: `logs/media_report.log`
- HTML 리포트: `reports/html/`
- Markdown 리포트: `reports/markdown/`

## 8. 트러블슈팅
- `Webhook URL 미설정` 경고
  - `.env`의 `SLACK_WEBHOOK_URL` 확인
- 이메일 발송 실패
  - SMTP 계정/앱 비밀번호/포트 확인
- 요약이 비어 있음
  - `GEMINI_API_KEY` 및 쿼터 확인
- Naver 수집량이 낮음
  - `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` 확인

## 9. 협업자가 바로 구현/확장하는 방법
- 수집기 추가: `collectors/`에 모듈 추가 후 `scheduler/jobs.py`에 연결
- 알림 채널 추가: `notifiers/`에 모듈 추가 후 파이프라인에 연결
- 분류 로직 변경: `processors/classifier.py`
- 리포트 포맷 확장: `reporters/` 및 `reporters/templates/`
- 웹 화면 확장: `web/templates/`, `web/static/`, `web/app.py`

## 10. GitHub 업데이트 절차
현재 폴더가 Git 저장소로 초기화되어 있지 않다면 아래 순서로 진행한다.

```bash
# 1) 저장소 초기화
git init

# 2) 원격 저장소 연결 (본인 GitHub URL로 변경)
git remote add origin https://github.com/<YOUR_ID>/<YOUR_REPO>.git

# 3) 파일 스테이징/커밋
git add .
git commit -m "docs: add prd and onboarding guide"

# 4) 기본 브랜치 설정 후 푸시
git branch -M main
git push -u origin main
```

이미 Git 저장소라면 2~4단계만 수행하면 된다.
