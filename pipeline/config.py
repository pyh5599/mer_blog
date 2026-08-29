import os
from pathlib import Path

BLOG_ID = "ranto28"
RSS_URL = f"https://rss.blog.naver.com/{BLOG_ID}.xml"
POST_URL = "https://blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}"
POST_PUBLIC_URL = f"https://blog.naver.com/{BLOG_ID}/{{log_no}}"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REQUEST_TIMEOUT = 20
REQUEST_DELAY_SEC = 1.5

LANGUAGE_CODE = "ko-KR"
VOICE_NAME = os.environ.get("TTS_VOICE", "ko-KR-Neural2-A")
SPEAKING_RATE = 1.0
MAX_SSML_BYTES = 4500
TTS_ENDPOINT = "https://texttospeech.googleapis.com/v1beta1/text:synthesize"

ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = ROOT / "site"
POSTS_DIR = SITE_DIR / "posts"
INDEX_PATH = SITE_DIR / "index.json"
FEED_PATH = SITE_DIR / "feed.xml"
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://example.github.io/mer_blog").rstrip("/")
DEFAULT_BACKFILL = 30
