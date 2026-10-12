"""Model-backed social hotspot lookup.

The hotspot radar used to read public RSS feeds.  Those feeds are either
unreachable from mainland China or return nothing for a narrow topic, so this
module asks the already-configured model instead: one request when the page is
opened, then a random subset of what came back is shown.

Two honesty rules are enforced here rather than left to the caller:

* every item is labelled as model output and explicitly unverified -- a model
  can be stale or simply wrong about current events;
* a URL written by the model is discarded, because invented links are exactly
  the kind of confident fabrication this project must not present as a source.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event
from typing import Callable

from .hotspots import HotspotCache, HotspotFetchResult, HotspotItem
from .jsonutil import load_json_object

MODEL_PUBLISHER = "模型生成"
MODEL_CREDIBILITY = "未核验（模型生成）"
UNVERIFIED_NOTE = "模型生成的社会热点，未核验：可能不准确或过时，不能当作新闻事实"


def build_hotspot_prompt(pool_size: int, topic: str) -> str:
    focus = (
        f"其中一半左右要与你关注的主题相关：{topic.strip()}。"
        "相关的条目把 related 填 true，其余填 false。"
        if topic.strip() else
        "本次没有指定主题，所有条目的 related 一律填 false。"
    )
    return (
        "你是中文社会热点编辑。请列出当下公众真的在讨论、有看头的社会热点，国内与国际都要有。\n"
        "只输出一个 JSON 对象，不要 markdown，不要代码围栏，不要解释。\n"
        "要求：\n"
        f"1. 一共 {pool_size} 条，其中国内（domestic）与国际（international）各占一半。\n"
        "2. 每条包含 title（不超过 30 字，要具体、有信息量，不要写成口号）、"
        "summary（一句话，不超过 60 字，说清为什么值得关注）、"
        "region（只能是 domestic 或 international）、category（社会／经济／科技／民生／文化 等）、"
        "when（这件事发生或被报道的时间，例如 2026年10月、2024年4月；"
        "确实不确定时就写 时间不确定，不要猜）、"
        "source（你记忆中报道它的媒体或渠道，例如 新华社、路透社、社交媒体热议；"
        "确实不确定时就写 来源不确定，不要猜）、"
        "related（true 或 false）。\n"
        f"3. {focus}\n"
        "4. 优先挑最近发生的。更早的事情也可以写，但 when 必须如实填写它发生的时间，"
        "绝不能把旧事说成当下热点。\n"
        "5. 优先挑有意思的：有冲突、有反差、有具体人物或场景、能让人想接着聊的事；"
        "避免空泛的会议表态、例行通报、纯宣传式条目。\n"
        f"6. 这 {pool_size} 条要分散在不同领域和不同地区，不要连续重复同一类话题。\n"
        "7. 不要编造具体数字、人名、机构名或链接；不要输出 url 字段。\n"
        'JSON 形状：{"items":[{"title":"...","summary":"...","region":"domestic",'
        '"category":"社会","when":"2026年10月","source":"新华社","related":false}]}'
    )


def parse_hotspot_items(text: str, fetched_at: datetime, topic: str) -> list[HotspotItem]:
    data = load_json_object(text)
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("热点结果缺少 items 列表")
    asked = bool(topic.strip())
    items: list[HotspotItem] = []
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        title = entry.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        region = entry.get("region")
        summary = entry.get("summary")
        category = entry.get("category")
        when = entry.get("when")
        source = entry.get("source")
        when_text = when.strip()[:40] if isinstance(when, str) and when.strip() else "时间不确定"
        source_text = source.strip()[:60] if isinstance(source, str) and source.strip() else "来源不确定"
        items.append(HotspotItem(
            title=title.strip()[:120],
            url="",
            summary=(summary.strip()[:300] if isinstance(summary, str) else ""),
            publisher=MODEL_PUBLISHER,
            region=region if region in {"domestic", "international"} else "international",
            category=(category.strip()[:20] if isinstance(category, str) and category.strip() else "社会"),
            published_at=None,
            fetched_at=fetched_at,
            credibility=MODEL_CREDIBILITY,
            related=bool(entry.get("related")) and asked,
            time_note=f"时间：{when_text} · 来源：{source_text}（均为模型自述，未核验）",
        ))
    return items


@dataclass
class ModelHotspotProvider:
    """Same interface as the RSS provider, but backed by the configured model."""

    complete: Callable[..., str]
    cache: HotspotCache | None = None
    max_items: int = 10
    pool_size: int = 30
    rng: random.Random | None = None

    def __post_init__(self) -> None:
        self.max_items = max(1, int(self.max_items))
        self.pool_size = max(self.max_items, int(self.pool_size))
        self.cache = self.cache or HotspotCache()
        self.rng = self.rng or random.Random()

    def fetch(self, topic: str = "", *, cancel_event: Event | None = None) -> HotspotFetchResult:
        topic = (topic or "").strip()
        cancelled = cancel_event or Event()
        if cancelled.is_set():
            return HotspotFetchResult([], success=False, message="刷新已取消")

        generation = self.cache.begin_refresh() if isinstance(self.cache, HotspotCache) else None
        fetched_at = datetime.now(timezone.utc)
        items: list[HotspotItem] = []
        failure = ""
        try:
            raw = self.complete(build_hotspot_prompt(self.pool_size, topic))
            items = parse_hotspot_items(raw, fetched_at, topic)
            if not items:
                failure = "模型没有返回可用热点"
        except Exception as exc:  # never let a hotspot lookup break the page
            failure = f"模型热点获取失败：{type(exc).__name__}"

        if cancelled.is_set():
            return HotspotFetchResult([], attempted=True, success=False, message="刷新已取消")

        if failure:
            cached, last_success = self.cache.load(topic=topic)
            if cached:
                return HotspotFetchResult(
                    cached, attempted=True, success=False, used_cache=True,
                    message=f"{failure}；已保留上次结果（缓存，{UNVERIFIED_NOTE}）",
                    fetched_at=fetched_at, last_success_at=last_success,
                )
            return HotspotFetchResult(
                [], attempted=True, success=False,
                message=f"{failure}；暂无可用热点（{UNVERIFIED_NOTE}）",
                fetched_at=fetched_at,
            )

        picked = self.rng.sample(items, min(self.max_items, len(items)))
        picked.sort(key=lambda item: (item.region != "domestic", item.title))
        self.cache.save_if_current(picked, fetched_at, generation, topic=topic)
        return HotspotFetchResult(
            picked, attempted=True, success=True,
            message=f"{UNVERIFIED_NOTE}（本条为 {len(picked)} 条）",
            fetched_at=fetched_at, last_success_at=fetched_at,
        )
