# MediaReporting

기업 뉴스 모니터링 자동화 시스템.

- PRD(스펙): [prd.md](prd.md)
- 설치/운영 가이드: [read.md](read.md)

## 빠른 시작

### 1) 설치
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2) 필수 환경변수 설정
- COMPANY_NAME
- KEYWORDS
- NAVER_CLIENT_ID
- NAVER_CLIENT_SECRET
- GEMINI_API_KEY

선택(권장):
- SLACK_WEBHOOK_URL
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_RECIPIENTS

### 3) 실행
```bash
python main.py
```

웹 대시보드:
```bash
python web/app.py
```
기본 주소: http://localhost:5100

## 배포
Vercel 배포 구성 포함:
- vercel.json
- api/index.py

배포 명령:
```bash
vercel --prod
```

환경변수 상세 및 운영 방법은 [read.md](read.md) 참고.
