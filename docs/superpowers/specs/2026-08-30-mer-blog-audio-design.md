# 메르의 블로그 오디오 — 설계 문서

작성일: 2026-08-30

## 목적

네이버 블로그 "메르의 블로그"(`blog.naver.com/ranto28`)의 새 글을 매일 자동으로 수집해 TTS로 변환하고,
Android 폰 브라우저에서 **들으면서 캡션을 읽을 수 있는** 웹 앱을 제공한다.
사용자는 육아·설거지 중인 한 명(wife). 손을 쓰지 않고도 재생·이어듣기가 되고,
멀리서도 읽을 수 있는 큰 글씨 캡션이 재생 위치를 따라 하이라이트된다.

## 결정 사항 (브레인스토밍 결과)

| 항목 | 결정 | 이유 |
|---|---|---|
| 전달 방식 | 정적 웹 앱 (PWA) | 캡션 커스텀 필요. 팟캐스트 앱은 transcript 스타일 제어 불가 |
| 대상 기기 | Android Chrome | Media Session·백그라운드 재생·PWA 전부 지원 |
| TTS | Google Cloud TTS `ko-KR-Neural2-A`, REST + API key | 월 100만 자 무료, SSML mark 타임스탬프 지원 |
| 실행/호스팅 | GitHub Actions cron + GitHub Pages | 무료, Mac 꺼져 있어도 동작 |
| 초기 범위 | 최근 30개 백필, 이후 새 글만 | RSS가 최근 50개까지 제공 |
| 스택 | Python 3.11 파이프라인 + vanilla HTML/JS | 빌드 도구 없음, 장기 유지보수 최소 |

RSS 피드(`feed.xml`)는 같은 mp3를 재사용하는 보너스 산출물로 포함한다 (팟캐스트 앱 구독도 가능).

## 저장소 구조

```
mer_blog/
├── pipeline/
│   ├── fetch.py        # RSS 파싱, PostView 크롤링
│   ├── clean.py        # HTML → 문장 배열
│   ├── tts.py          # 문장 배열 → mp3 + 문장별 타임스탬프
│   ├── feed.py         # index.json → feed.xml (RSS)
│   ├── run.py          # 오케스트레이션, CLI
│   ├── config.py       # blogId, voice, 경로 등 상수
│   └── tests/          # pytest (clean, tts 청킹/오프셋, feed)
├── site/               # GitHub Pages 산출물 (Actions가 배포)
│   ├── index.html, app.js, style.css
│   ├── manifest.webmanifest, sw.js, icon.svg
│   ├── index.json      # 글 목록 (최신순)
│   ├── feed.xml
│   └── posts/<logNo>.mp3, <logNo>.json
├── .github/workflows/daily.yml
├── requirements.txt
└── README.md
```

## 파이프라인

### fetch.py

- `list_recent_posts() -> list[PostRef]` — `https://rss.blog.naver.com/ranto28.xml` 파싱.
  `PostRef = {log_no, title, published(ISO), url}`. `guid`에서 `logNo` 추출.
- `fetch_post_html(log_no) -> str` — `https://blog.naver.com/PostView.naver?blogId=ranto28&logNo=<log_no>` GET.
  User-Agent 지정, timeout 20s, 실패 시 예외. 호출자가 글 사이 1.5초 sleep.

### clean.py

- `extract_sentences(html) -> list[str]`
  - `div.se-main-container` 안에서 `p.se-text-paragraph` 텍스트만 수집 (BeautifulSoup).
  - 제외: `.se-caption`(이미지 캡션), `.se-oglink`(링크 카드), `.se-table`, `.se-code`.
  - 구버전 에디터(`#postViewArea`) 폴백: `<p>`, `<div>` 텍스트.
  - 제로폭 공백(`​`) 제거, 연속 공백 정리, URL 토큰 제거, 빈 줄 제거.
  - 문단 안에서 `. ? !` 뒤 공백 기준으로 추가 분리. 숫자 목록 `1.` 같은 접두는 분리하지 않음
    (정규식: 종결부호 뒤 공백 + 다음 문자가 숫자+점이 아닐 때).
  - 첫 문장이 제목과 동일하면 제거 (본문 첫 줄에 제목이 반복됨).
- 결과 문장 길이 상한 없음. 빈 결과면 `EmptyPostError`.

### tts.py

- `synthesize(sentences, voice) -> (mp3_bytes, starts: list[float], duration: float)`
- 청킹: 문장을 순서대로 모아 SSML 바이트 길이 4,500 이하 청크로 묶음.
  청크 SSML: `<speak><mark name="s{i}"/>{escaped text}<break time="300ms"/>...</speak>`.
- 요청: `POST https://texttospeech.googleapis.com/v1beta1/text:synthesize?key=...`
  body `{input:{ssml}, voice:{languageCode:"ko-KR", name}, audioConfig:{audioEncoding:"MP3", speakingRate:1.0}, enableTimePointing:["SSML_MARK"]}`.
  응답 `audioContent`(base64), `timepoints:[{markName, timeSeconds}]`.
- 청크 mp3 길이는 mutagen으로 측정(ffmpeg 불필요). 청크별 timepoint에 누적 오프셋을 더해 전체 `starts` 생성.
- 청크 mp3 결합: CBR mp3 바이트 결합 (Google 출력은 ID3 없는 CBR 프레임 스트림).
- timepoints가 비어 있으면(음성이 미지원) 문자 수 비례로 시작 시각 추정 — 로그에 경고.
- 재시도: HTTP 429/5xx는 지수 백오프 3회.

### feed.py

- `build_feed(index, base_url) -> str` — RSS 2.0 + `<enclosure>` mp3. iTunes 네임스페이스 최소 태그.

### run.py

```
python pipeline/run.py [--limit N] [--backfill N] [--dry-run] [--log-no ID]
```

1. `site/index.json` 로드 (없으면 빈 목록).
2. RSS 목록 중 `index.json`에 없는 `log_no` 필터. `index.json`이 비어 있으면 최신 `--backfill`(기본 30)개로 제한, 아니면 전부.
3. 오래된 글부터 순서대로: fetch → clean → tts → `site/posts/<id>.mp3`, `<id>.json` 저장 → index 항목 추가 → `index.json` 즉시 저장 (중간 실패 시 진행분 보존).
4. 글 하나 실패 시 예외 로그 후 다음 글 계속. 마지막에 실패 목록 출력, 실패 있으면 exit code 1 (Actions 알림용). 커밋은 실패와 무관하게 진행.
5. `feed.xml` 재생성.

`posts/<id>.json` 스키마:

```json
{
  "id": "224394691017",
  "title": "중국이 외국인을 들여다 보는 법",
  "published": "2026-08-30T08:05:08+09:00",
  "url": "https://blog.naver.com/ranto28/224394691017",
  "duration": 512.3,
  "sentences": [{"text": "…", "start": 0.0}, …]
}
```

`index.json` 스키마: `[{id, title, published, duration}]` 최신순.

### GitHub Actions (`daily.yml`)

- 트리거: `schedule` 매일 `0 22 * * *`, `0 4 * * *`(UTC; KST 07:00, 13:00) + `workflow_dispatch`.
- 단계: checkout → setup-python 3.11 → pip install → `python pipeline/run.py`
  (`GOOGLE_TTS_API_KEY` secret) → `site/` 변경 있으면 커밋·푸시 (`github-actions[bot]`) → `actions/upload-pages-artifact`(site/) → `actions/deploy-pages`.
- `concurrency` 그룹으로 동시 실행 방지.

## 웹 앱 (`site/`)

단일 페이지, 프레임워크 없음. 화면 두 개를 JS로 전환.

### 목록 화면

- 상단 제목 "메르의 블로그", 오른쪽에 글씨 크기 버튼(A-/A+).
- `index.json` 로드 → 카드 목록: 제목, 날짜, 길이(분), 진행률 바(들은 위치/전체), 완료 체크.
- 탭하면 플레이어 화면.

### 플레이어 화면

- 상단: 뒤로, 제목.
- 본문: 문장을 `<p>`로 나열. 현재 문장 `.active` 강조(배경색 + 굵게), 지난 문장은 흐리게.
  현재 문장이 화면 중앙에 오도록 `scrollIntoView({block:"center", behavior:"smooth"})`.
  사용자가 직접 스크롤하면 5초간 자동 스크롤 중단.
- 문장 탭 → 해당 `start`로 seek.
- 하단 고정 컨트롤: 15초 뒤로 / 재생·일시정지 / 15초 앞으로, 진행 슬라이더, 시간, 배속(1.0/1.2/1.5/2.0 순환).
- `<audio>` 하나 재사용. `timeupdate`마다 이진 탐색으로 현재 문장 인덱스.
- 재생 위치 저장: `localStorage["pos:<id>"]` 5초마다 + pause/ended 시. 재개 시 복원. `ended`면 완료 표시 후 다음(더 오래된) 글 자동 재생.
- Media Session API: 제목/아티스트("메르의 블로그") 설정, play/pause/seekbackward/seekforward/nexttrack/previoustrack 핸들러 → 잠금화면·이어폰 컨트롤.
- 글씨 크기: 18/22/26/30px 단계, `localStorage["fontSize"]`.
- 다크 모드: `prefers-color-scheme` 따라감.

### PWA

- `manifest.webmanifest`: 이름, `display: standalone`, 아이콘(SVG), 테마색.
- `sw.js`: 앱 셸(index.html, app.js, style.css)만 캐시. `index.json`·`posts/*`는 network-first, 오프라인이면 캐시 폴백. mp3는 캐시하지 않음 (용량).

## 오류 처리 요약

| 지점 | 처리 |
|---|---|
| RSS 다운/파싱 실패 | run 즉시 실패, exit 1 (다음 cron에 재시도) |
| 글 fetch/clean/tts 실패 | 그 글만 건너뜀, 로그, 다음 실행 때 재시도 (index에 없으므로) |
| TTS 429/5xx | 지수 백오프 3회 후 글 실패 처리 |
| timepoint 없음 | 문자 수 비례 추정 + 경고 |
| 웹: index.json 로드 실패 | "불러오기 실패, 다시 시도" 버튼 |
| 웹: mp3 로드 실패 | 플레이어에 오류 표시, 목록으로 복귀 가능 |

## 테스트

- `pipeline/tests/test_clean.py`: 저장된 실제 HTML 샘플(fixture)로 문장 추출, 캡션·링크 제외, 문장 분리, 제목 중복 제거.
- `pipeline/tests/test_tts.py`: 청킹(4,500바이트 경계, 문장 안 잘림), 오프셋 누적, 폴백 추정. HTTP는 mock.
- `pipeline/tests/test_feed.py`: feed.xml 필수 태그.
- `pipeline/tests/test_run.py`: 미처리 필터 + backfill 제한 로직 (fetch/tts mock).
- 웹 앱: 로컬 `python -m http.server`로 수동 확인 (Chrome 모바일 에뮬레이션). 자동 테스트 없음.

## 사용자가 해야 할 일 (마지막에 한 번에)

1. Google Cloud 프로젝트에서 Text-to-Speech API 활성화, API key 발급 (TTS API로만 제한).
2. GitHub에 repo 생성, push.
3. repo Settings → Secrets → `GOOGLE_TTS_API_KEY` 등록.
4. Settings → Pages → Source: GitHub Actions.
5. Actions에서 `daily` 워크플로 수동 실행 (첫 백필).
6. wife 폰 Chrome으로 `https://<user>.github.io/mer_blog/` 접속 → 홈 화면에 추가.

## 범위 밖 (YAGNI)

- 50개 초과 과거 글 크롤링
- 푸시 알림
- 다중 사용자/로그인
- 서버 사이드 재생 위치 동기화
