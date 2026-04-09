# MediaReporting 설치/운영 가이드 (초보자용)

이 문서는 처음 사용하는 사람도 그대로 따라 하면 실행할 수 있도록 작성했습니다.

## 0. 먼저 이해하기
- 이 프로젝트는 회사 관련 뉴스를 자동으로 모아서 위험도를 판단하고, 요약 리포트를 만들어 줍니다.
- 실행하면 결과가 DB와 리포트 파일로 저장되고, 필요하면 Slack/이메일로도 보냅니다.

용어 정리:
- 가상환경: 프로젝트 전용 파이썬 실행 공간
- .env: 내 API 키와 개인 설정을 담는 파일
- 파이프라인: 수집 -> 중복제거 -> 분류 -> 요약 -> 리포트 생성 전체 흐름

## 1. 준비물
- macOS, Linux, WSL 중 하나
- Python 3.10 이상
- 인터넷 연결
- API 키 3개
  - NAVER_CLIENT_ID
  - NAVER_CLIENT_SECRET
  - GEMINI_API_KEY

선택 준비물:
- Slack Webhook URL
- SMTP 계정 정보
- Vercel CLI (배포할 때만 필요)

## 2. 설치 (복사해서 순서대로 실행)
```bash
cd MediaReporting
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

팁:
- 터미널을 새로 열 때마다 source .venv/bin/activate 를 다시 실행해야 합니다.

## 3. .env 설정 (가장 중요)
.env 파일을 열고 아래 항목을 채워주세요.

필수:
- COMPANY_NAME: 회사명
- KEYWORDS: 검색할 키워드 (쉼표 구분)
- NAVER_CLIENT_ID
- NAVER_CLIENT_SECRET
- GEMINI_API_KEY

예시:
```env
COMPANY_NAME=삼성전자
KEYWORDS=삼성전자,Samsung,반도체,갤럭시
NAVER_CLIENT_ID=xxxxxxxx
NAVER_CLIENT_SECRET=xxxxxxxx
GEMINI_API_KEY=xxxxxxxx
```

선택(알림):
- SLACK_WEBHOOK_URL
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_RECIPIENTS

## 4. API 키 발급 위치
- Naver API
  - https://developers.naver.com
  - 애플리케이션 생성 후 Client ID, Client Secret 발급
- Gemini API
  - https://aistudio.google.com/apikey
  - API key 생성 후 GEMINI_API_KEY에 입력
- Slack Webhook
  - https://api.slack.com/apps
  - Incoming Webhook 활성화 후 URL 복사

## 5. 첫 실행 (정상 동작 확인)

### 5-1. 파이프라인 1회 실행
```bash
python main.py --run now
```

### 5-2. 결과 확인
아래가 생성되면 정상입니다.
- data/articles.db
- reports/html 아래 html 파일
- reports/markdown 아래 md 파일

### 5-3. 웹 화면 실행
```bash
python web/app.py
```

브라우저 접속:
- http://localhost:5100

## 6. 운영 명령어 모음
- 전체 운영(정기 + 실시간):
```bash
python main.py
```
- 즉시 1회 실행:
```bash
python main.py --run now
```
- 감사 리포트만:
```bash
python main.py --run audit
```
- 모니터만:
```bash
python main.py --monitor-only
```
- 로그 조회/검색/메모:
```bash
python main.py --log 2026-04-09
python main.py --search 소송
python main.py --note 2026-04-09 "대응 완료"
```

## 7. Vercel 배포

### 7-1. 배포
```bash
vercel --prod
```

### 7-2. 환경변수 등록
Vercel 프로젝트의 Environment Variables에 .env 값을 그대로 등록합니다.

등록 권장 목록:
- COMPANY_NAME
- KEYWORDS
- NAVER_CLIENT_ID
- NAVER_CLIENT_SECRET
- GEMINI_API_KEY
- SLACK_WEBHOOK_URL
- SMTP_HOST
- SMTP_PORT
- SMTP_USER
- SMTP_PASS
- EMAIL_RECIPIENTS
- MONITOR_INTERVAL_SECONDS
- AUDIT_MIN_ARTICLES

등록 후 재배포:
```bash
vercel --prod
```

## 8. 자주 생기는 문제와 해결
- 문제가 1: 수집 기사가 거의 없음
  - 원인: Naver 키 누락/오타
  - 해결: NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 다시 확인
- 문제가 2: 요약이 비어 있음
  - 원인: Gemini 키 누락, 쿼터 소진
  - 해결: GEMINI_API_KEY 확인, 사용량 확인
- 문제가 3: Slack 알림이 안 옴
  - 원인: Webhook URL 누락/잘못된 URL
  - 해결: SLACK_WEBHOOK_URL 재확인
- 문제가 4: 이메일 발송 실패
  - 원인: SMTP 계정 또는 앱 비밀번호 문제
  - 해결: SMTP_USER, SMTP_PASS, SMTP_PORT 확인

## 9. 파일 구조를 쉽게 보면
- 실행 시작점: main.py
- 웹 화면: web/app.py
- 뉴스 수집: collectors/
- 기사 처리(분류/요약): processors/
- 리포트 생성: reporters/
- 알림 발송: notifiers/
- DB 로직: storage/database.py

## 10. 팀원이 바로 확장하려면
- 뉴스 소스 추가: collectors/ 에 새 모듈 추가 후 scheduler/jobs.py에 연결
- 알림 채널 추가: notifiers/ 에 새 모듈 추가
- 리스크 규칙 조정: processors/classifier.py 수정
- 리포트 템플릿 변경: reporters/templates/ 수정
- 웹 화면 변경: web/templates/ 및 web/app.py 수정
