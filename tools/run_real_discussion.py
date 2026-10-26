"""Run one real, full discussion end to end and export it.

This exists because unit tests cannot tell you whether the real-model path is
usable.  It follows the same route the desktop app takes: initial generation,
then one turn per user step, then a closing summary, and finally the app's own
Markdown/JSON export.

Refuses to run against the offline simulator: a simulated discussion must never
be presented as evidence that the real path works.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from brainstorm.ai_settings import AISettingsStore
from brainstorm.config import AppConfig
from brainstorm.export import export_json, export_markdown
from brainstorm.llm import ProviderFailure, TurnSpec
from brainstorm.providers import resolve_providers
from brainstorm.roles import DEFAULT_ROLES, EVENT_ROLES, face_label


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("topic")
    parser.add_argument("--extra", type=int, default=6, help="首批之后逐条追加的发言数")
    parser.add_argument("--section", choices=("business", "event"), default="business",
                        help="business=商业痛点九个职业席位；event=事件讨论八个八卦席位")
    parser.add_argument("--out", default="artifacts")
    args = parser.parse_args()

    roles = EVENT_ROLES if args.section == "event" else DEFAULT_ROLES

    config = AISettingsStore().load(AppConfig.from_environment())
    provider, _news, status = resolve_providers(config)
    print(f"[i] provider={status.discussion_provider} mode={status.effective_mode} "
          f"model={status.model_name} fallback={status.fallback_reason or '无'}", flush=True)
    if status.discussion_provider == "mock":
        print("[x] 真实模型不可用，拒绝用离线模拟冒充验证结果", flush=True)
        return 2

    started = time.perf_counter()

    print("[i] 首批生成中……", flush=True)
    t = time.perf_counter()
    try:
        session = provider.discuss(args.topic, roles)
    except ProviderFailure as exc:
        print(f"[x] 首批失败: {exc.code} / {exc.safe_message}", flush=True)
        return 3
    print(f"[i] 首批 {len(session.utterances)} 条，用时 {time.perf_counter() - t:.1f}s", flush=True)
    for index, item in enumerate(session.utterances, 1):
        print(f"    {index:2d}. {item.speaker_name} · {item.phase} · {item.kind.value} · {item.intent}"
              f" · {face_label(item.face) or '—'}", flush=True)

    for step in range(args.extra):
        session.rebuild_state()
        t = time.perf_counter()
        try:
            added = provider.extend_batch(session, session.discussion_state, roles=roles)
        except ProviderFailure as exc:
            print(f"[!] 追加第 {step + 1} 条失败: {exc.code} / {exc.safe_message}", flush=True)
            break
        item = session.append_utterance(added[0])
        # Mirror what the app's controller does with the orchestrator's in-request
        # state refresh; without this the exported state looks empty even when the
        # refresh worked, which would misreport the run.
        refresh = getattr(provider, "last_state_refresh", None)
        if refresh is not None:
            session.discussion_state.consensus = list(refresh.consensus)
            session.discussion_state.conflicts = list(refresh.conflicts)
            session.discussion_state.unresolved_questions = list(refresh.unresolved)
            provider.last_state_refresh = None
        note = f" · 质检重写：{item.review_note}" if item.review_note else ""
        print(f"[{step + 1}/{args.extra}] {item.speaker_name} · {item.phase} · {item.intent}"
              f" · {face_label(item.face) or '—'} · 回应={item.replies_to or '无'} ({time.perf_counter() - t:.1f}s){note}", flush=True)

    print("[i] 生成结束总结中……", flush=True)
    t = time.perf_counter()
    try:
        final = provider.generate_turn(
            session.topic, roles, list(session.sources), list(session.utterances),
            TurnSpec("moderator", "主持人", "阶段总结", "总结", final=True),
        )
        session.append_utterance(final.utterance)
        if final.opportunity:
            session.opportunity = final.opportunity
        print(f"[i] 总结用时 {time.perf_counter() - t:.1f}s；机会档案="
              f"{'有' if session.opportunity else '无'}", flush=True)
    except ProviderFailure as exc:
        print(f"[!] 总结失败: {exc.code} / {exc.safe_message}", flush=True)

    session.rebuild_state()
    session.provider_mode = "llm"
    session.effective_provider = provider.provider_name
    session.request_mode = "llm"
    session.model_name = status.model_name
    session.status_message = "真实模型生成；观点与来源仍需核验"
    session.usage_requests = provider.last_usage.requests
    session.usage_input_tokens = provider.last_usage.input_tokens
    session.usage_output_tokens = provider.last_usage.output_tokens

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    md = export_markdown(session, out_dir / f"real-{stamp}.md")
    js = export_json(session, out_dir / f"real-{stamp}.json")

    print(f"[i] 总用时 {time.perf_counter() - started:.1f}s", flush=True)
    print(f"[i] 发言 {len(session.utterances)} 条；请求 {provider.last_usage.requests} 次；"
          f"输入 {provider.last_usage.input_tokens} / 输出 {provider.last_usage.output_tokens} tokens", flush=True)
    print(f"[i] 导出: {md}", flush=True)
    print(f"[i] 导出: {js}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
