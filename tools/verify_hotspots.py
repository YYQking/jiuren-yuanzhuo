"""Probe public default feeds; keep QA cache and evidence in the workspace."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from brainstorm.config import DEFAULT_RSS_FEEDS
from brainstorm.hotspots import HotspotCache, HotspotProvider, default_hotspot_feeds


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "人工智能"
    output = Path(sys.argv[2] if len(sys.argv) > 2 else "artifacts/hotspots-network.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    feeds = default_hotspot_feeds(DEFAULT_RSS_FEEDS)

    def check(index_feed):
        index, feed = index_feed
        errors = []
        def read(url, timeout):
            try:
                return HotspotProvider._read_url(url, timeout)
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                raise
        provider = HotspotProvider([feed], timeout=8, max_items=3,
                                   transport=read,
                                   cache=HotspotCache(output.parent / "hotspots-network-cache" / f"{index}.json"))
        result = provider.fetch(topic)
        return {"feed": feed.url.replace("{query}", quote(topic + " when:2d", safe="")),
                "region": feed.region, "category": feed.category,
                "related": feed.related, "success": result.success,
                "used_cache": result.used_cache, "status": result.message,
                "errors": errors,
                "count": len(result.items),
                "examples": [{"title": item.title, "publisher": item.publisher, "url": item.url,
                              "published_at": item.published_at.isoformat() if item.published_at else None}
                             for item in result.items[:2]]}

    with ThreadPoolExecutor(max_workers=5) as pool:
        rows = list(pool.map(check, enumerate(feeds)))
    evidence = {"checked_at": datetime.now(timezone.utc).isoformat(), "topic": topic, "feeds": rows}
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(output), "total": len(rows),
                      "successful": sum(row["success"] and not row["used_cache"] for row in rows),
                      "domestic_items": sum(row["count"] for row in rows if row["region"] == "domestic"),
                      "international_items": sum(row["count"] for row in rows if row["region"] == "international"),
                      "failures": [row["errors"] for row in rows if not row["success"]]}, ensure_ascii=False))
    return 0 if any(row["success"] and not row["used_cache"] and row["count"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
