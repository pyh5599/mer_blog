# 메르의 블로그 오디오

네이버 블로그 [메르의 블로그](https://blog.naver.com/ranto28) 글을 매일 자동으로 TTS(mp3)로 변환하고,
문장 단위 캡션이 재생 위치를 따라 하이라이트되는 웹 앱(PWA)으로 제공합니다.
GitHub Actions가 하루 두 번 새 글을 확인하고 GitHub Pages에 배포합니다.

설계 문서: `docs/superpowers/specs/2026-08-30-mer-blog-audio-design.md`

## 구조

```
pipeline/   RSS → 본문 크롤링 → 문장 정제 → Google TTS → site/ 산출물
site/       정적 웹 앱 (GitHub Pages 루트) + posts/<id>.mp3|json + index.json + feed.xml
.github/workflows/daily.yml   cron 실행 + 커밋 + Pages 배포
```

## 최초 설정 (한 번만)

1. **Google Cloud**: 프로젝트 생성 → *Cloud Text-to-Speech API* 활성화 → API 키 발급.
   키 제한: "API 제한"에서 Cloud Text-to-Speech API만 허용 권장.
2. **GitHub repo** 생성 후 이 디렉토리를 push.
3. repo **Settings → Secrets and variables → Actions → New repository secret**:
   `GOOGLE_TTS_API_KEY` = 발급한 키.
4. **Settings → Pages → Build and deployment → Source: GitHub Actions**.
5. **Actions → daily → Run workflow** 수동 실행. 첫 실행은 최근 30개 글을 백필합니다 (10분 내외).
6. 폰 Chrome에서 `https://<github계정>.github.io/<repo이름>/` 접속 → 메뉴 → *홈 화면에 추가*.

이후엔 매일 01:00 / 14:00 KST에 새 글이 자동으로 추가됩니다.

팟캐스트 앱으로 듣고 싶으면 같은 주소의 `feed.xml`을 구독하면 됩니다 (캡션은 없음).

## 로컬 실행

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest                                   # 테스트
.venv/bin/python -m pipeline.run --dry-run         # 처리 예정 글 목록만 출력
GOOGLE_TTS_API_KEY=... .venv/bin/python -m pipeline.run --limit 1   # 글 1개만 변환
cd site && python3 -m http.server 8000             # http://localhost:8000 에서 앱 확인
```

옵션: `--limit N` 이번 실행에서 최대 N개, `--backfill N` 첫 실행 백필 개수(기본 30),
`--log-no <id>` 특정 글만 (재생성).

## 설정

- 비밀번호: 앱 첫 진입 시 한 번 묻고 브라우저에 기억합니다. 바꾸려면 `site/app.js`의 `PW_HASH`를
  새 비밀번호의 FNV-1a 해시로 교체 (`node -e "let h=2166136261;for(const c of '새비번'){h^=c.charCodeAt(0);h=Math.imul(h,16777619)>>>0}console.log(h)"`).
  클라이언트 검사라 지나가는 사람을 막는 용도이지 진짜 보안은 아닙니다 (mp3 URL 직접 접근 가능).
- 음성: 환경변수 `TTS_VOICE` (기본 `ko-KR-Chirp3-HD-Kore`, 여성). 남성은 `ko-KR-Chirp3-HD-Charon`.
  Chirp3-HD는 SSML 타임스탬프를 안 주므로 문장마다 따로 합성해 이어붙입니다 (글당 요청 40~60회).
  `ko-KR-Neural2-*`를 쓰면 청크 합성 + `<mark>` 타임스탬프 방식으로 동작합니다.
  Actions에서 바꾸려면 workflow의 "Run pipeline" step `env`에 `TTS_VOICE`를 추가.
  음성을 바꾼 뒤 기존 글을 다시 만들려면 `site/posts/`와 `site/index.json`(`[]`)을 비우고 실행.
- 속도: `pipeline/config.py`의 `SPEAKING_RATE`.
- 실행 시각: `.github/workflows/daily.yml`의 `cron` (UTC).

## 비용

Google TTS는 음성 등급별로 월 무료 구간이 있습니다 (Chirp3-HD·Neural2 각 100만 자 수준 — 결제 페이지에서 확인).
글 하나 약 3천 자, 월 30~40개면 무료 구간 안입니다.
GitHub Actions/Pages는 공개 repo에서 무료.

## 주의

- 블로그 원문 저작권은 저자(메르)에게 있습니다. 개인 청취 용도로만 사용하세요.
  repo를 **private**으로 만들 경우 GitHub Pages는 유료 플랜이 필요합니다.
- 네이버가 페이지 구조(`se-main-container`)를 바꾸면 `pipeline/clean.py` 셀렉터를 수정해야 합니다.
