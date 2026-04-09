# MediaReporting

기업 관련 뉴스를 자동으로 수집하고, 위험도를 분류하고, 요약 리포트를 만드는 프로젝트입니다.

처음 보는 분은 아래 순서대로만 따라오면 실행할 수 있습니다.

## 문서 안내
- 기능/스펙 문서: [prd.md](prd.md)
- 설치/운영 상세 문서: [read.md](read.md)

## 1. 이 프로젝트가 하는 일
- 뉴스 수집: Google News + Naver News
- 분석: 중복 제거, 리스크 분류, AI 요약
- 결과물: HTML/Markdown 리포트 생성
- 알림: Slack, 이메일 전송
- 화면: 웹 대시보드 제공

## 2. 정말 빠른 시작 (10분)

### 2-1. 설치
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2-2. .env 값 입력
아래 5개는 최소 필수입니다.
- COMPANY_NAME
- KEYWORDS
- NAVER_CLIENT_ID
- NAVER_CLIENT_SECRET
- GEMINI_API_KEY

예시:
```env
COMPANY_NAME=삼성전자
KEYWORDS=삼성전자,Samsung,반도체,갤럭시
NAVER_CLIENT_ID=발급받은값
NAVER_CLIENT_SECRET=발급받은값
GEMINI_API_KEY=발급받은값
```

### 2-3. 1회 실행 테스트
```bash
python main.py --run now
```

정상 동작하면 아래 위치에 결과가 생깁니다.
- DB: data/articles.db
- 리포트: reports/html, reports/markdown

### 2-4. 웹 화면 확인
```bash
python web/app.py
```

브라우저에서 접속:
- http://localhost:5100

## 3. 운영 모드
- 정기+실시간 운영: python main.py
- 즉시 1회 실행: python main.py --run now
- 감사 점검만 실행: python main.py --run audit
- 모니터만 실행: python main.py --monitor-only

## 4. 배포
이 저장소는 Vercel 배포 설정이 포함되어 있습니다.
- 설정 파일: vercel.json
- 서버리스 엔트리: api/index.py

배포 명령:
```bash
vercel --prod
```

## 5. 자주 막히는 지점
- 실행은 되는데 뉴스가 거의 없음
	- NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 확인
- 리포트에 요약이 비어 있음
	- GEMINI_API_KEY 확인
- Slack 알림이 오지 않음
	- SLACK_WEBHOOK_URL 확인
- 이메일이 오지 않음
	- SMTP_USER, SMTP_PASS, EMAIL_RECIPIENTS 확인

설정값 전체 설명은 [read.md](read.md)에서 확인할 수 있습니다.
