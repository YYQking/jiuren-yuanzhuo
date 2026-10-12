"""Check public feeds and save a compact network report without model credentials."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from brainstorm.config import DEFAULT_RSS_FEEDS
from brainstorm.news import RssNewsProvider


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "人工智能"
    output = Path(sys.argv[2] if len(sys.argv) > 2 else "artifacts/network-verification.json")
    urls = [url.replace("{query}", quote(topic, safe="")) for url in DEFAULT_RSS_FEEDS]

    def check(url):
        result = RssNewsProvider([url], timeout=8, max_items=3).fetch_with_status(topic)
        return {
            "feed": url, "attempted": result.attempted, "success": result.success,
            "matched": result.matched, "status": result.message,
            "sources": [{"title": item.title, "url": item.url,
                         "published_at": item.published_at.isoformat() if item.published_at else None}
                        for item in result.sources],
        }

    with ThreadPoolExecutor(max_workers=5) as pool:
        rows = list(pool.map(check, urls))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"topic": topic, "feeds": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
