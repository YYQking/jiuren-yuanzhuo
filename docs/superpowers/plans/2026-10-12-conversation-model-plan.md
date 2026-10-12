# 九人圆桌对话模型（第一期 + 第二期）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让真实模型路径真正产出协议要求的结构化标记（意图、回应对象、立场变化），并用一个不联网的本地调度器取代"按名册轮转"，使下一个发言人与回应对象由讨论内容决定。

**Architecture:** 新增 `brainstorm/turn_planner.py`，它是纯函数式、无副作用、不发请求、不依赖 Qt 的本地分析单元，产出结构事实（谁被反驳未回、哪个提问没人答、谁久未发言）与兜底计划。`brainstorm/llm.py` 的 `extend_batch` 从"按索引轮转"改为消费该计划；`generate_turn` 接受计划并把"本次必须回应谁、为什么"写进提示词。控制器与界面只做最小改动，把新的标记显示出来。

**Tech Stack:** Python 3、unittest（本项目**不用 pytest**）、PySide6/Qt、标准库 `urllib.request`（OpenAI 兼容路径无第三方 SDK）。

**本计划范围：** 设计文档 `docs/superpowers/specs/2026-10-12-conversation-model-design.md` 的第一期与第二期。第三期（编排层与质检层）、第四期（可靠性与长讨论）另行出计划——它们依赖本期实际产出的 `TurnPlan` 接口，提前写会写错。

---

## 全局约定（每个任务都适用）

**Python 解释器**（本机唯一可用）：

```
C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
```

**每个命令前先设置环境**（每次新开 shell 都要设）：

```powershell
$ws = (Resolve-Path '.').Path
$env:PYTHONPATH = $ws + ';' + (Resolve-Path '.qt-build-runtime').Path
$env:QT_QPA_PLATFORM = 'offscreen'
$py = 'C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
```

**运行单个测试模块**：

```powershell
& $py -m unittest tests.test_turn_planner -v
```

**运行全套**：

```powershell
& $py -m unittest discover -s tests
```

预期基线：**Ran 127 tests / OK**。

> **若全套命令"卡住"而不是失败**：这是 DSH 文件沙盒与 `tempfile.TemporaryDirectory()` 的交互问题（`mkstemp` 在 Windows 上把 `PermissionError` 误判为重名并重试约 10000 次），不是代码缺陷。改用 `& $py tools/run_tests_sandboxed.py`。详见 `PROJECT_MEMORY.md` 第 9 节。

**版本控制**：本项目当前**不是 git 仓库**。任务里的 commit 步骤仅在已初始化 git 后执行；若用户不同意初始化，则跳过 commit，改为"留存改动前文件副本"，并以"全套测试通过"作为该任务的终点。

**不要做的事**：不改 `brainstorm/engine.py`（离线路径保持原样）；不改存储格式（`storage.py` 的 schema 仍为 v6）；不新增 `Utterance` / `DiscussionState` 字段；不引入固定轮数上限；不做自动播放。

---

## 文件结构

| 文件 | 操作 | 职责 |
| --- | --- | --- |
| `brainstorm/turn_planner.py` | 新建 | 本地结构事实 + 兜底计划。纯函数，无网络、无 Qt |
| `tests/test_turn_planner.py` | 新建 | 调度器全部规则的单元测试 |
| `brainstorm/llm.py` | 修改 | 提示词索要结构化标记；解析取最新回指；统一剥代码围栏；`extend_batch` 接入调度器 |
| `brainstorm/session_controller.py` | 修改 | 在主场线程记录主持人介入原因 |
| `brainstorm/qt_app.py` | 修改 | 显示"回应 XXX"与介入原因 |
| `tests/test_b_integration.py` | 修改 | 提示词与解析的回归测试 |
| `tests/test_qt_ui.py` | 修改 | 界面标记的回归测试 |

---

## Task 0: 建立可回退基线

**Files:**
- 无代码改动

- [ ] **Step 1: 确认是否初始化 git**

先问用户。若同意：

```powershell
git init
git add -A
git commit -m "chore: 记录对话模型改造前的基线"
```

若不初始化 git，改为给将要修改的 4 个文件留副本：

```powershell
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
New-Item -ItemType Directory -Force -Path ".backup-$stamp" | Out-Null
Copy-Item brainstorm/llm.py, brainstorm/session_controller.py, brainstorm/qt_app.py, tests/test_b_integration.py ".backup-$stamp\"
"备份于 .backup-$stamp"
```

- [ ] **Step 2: 记录当前测试基线**

```powershell
& $py -m unittest discover -s tests
```

预期：`Ran 127 tests` 且 `OK`。若不是 127 或不是 OK，**停下来**先弄清差异，不要继续。

---

## Task 1: 提示词索要 intent、stance_change 与 event_id

这是整个改造的地基：调度器与后续质检都依赖这些标记，而当前提示词根本没要（`llm.py:238`），解析器却在读（`llm.py:329,332`）。

**Files:**
- Modify: `brainstorm/llm.py:229`（前文渲染）、`brainstorm/llm.py:238-247`（schema 与提示词正文）
- Test: `tests/test_b_integration.py`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_b_integration.py` 的 `BIntegrationTests` 类内（放在 `test_anthropic_parse_preserves_discussion_metadata` 之后）：

```python
    def test_prompt_requests_intent_stance_and_event_ids(self):
        captured = []

        class Event:
            text = '{"content":"回应","intent":"challenge"}'

        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])

        class Messages:
            def stream(self, **kwargs):
                captured.append(kwargs["messages"][0]["content"])
                return Stream()

        class Client:
            messages = Messages()

        provider = AnthropicDiscussionProvider(client=Client(), model="test-model")
        session = DiscussionSession(topic="数字服务", selected_role_ids=["r"])
        prior = session.append_utterance(Utterance("other", "另一角色", "现有观点", ViewpointKind.OPPORTUNITY, "独立观点", origin="model", intent="support"))
        provider.extend_batch(session, DiscussionState(), roles=[Role("r", "角色", "职责", "#fff", "提示")])
        prompt = captured[0]
        # 提示词必须索要意图、立场变化，并把 event_id 交给模型
        self.assertIn("intent", prompt)
        self.assertIn("stance_change", prompt)
        self.assertIn(prior.event_id, prompt)
        self.assertIn("support", prompt)
        self.assertIn("challenge", prompt)
        # 立场变化必须写明仍然保留的条件或疑虑（协议 §2.3 的第四项）
        self.assertIn("仍然保留的条件", prompt)
        # 必须明确禁止重复前文
        self.assertIn("不得重复", prompt)
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
& $py -m unittest tests.test_b_integration.BIntegrationTests.test_prompt_requests_intent_stance_and_event_ids -v
```

预期：FAIL。`AssertionError` 落在第一个 `assertIn("intent", prompt)` 或 `assertIn(prior.event_id, prompt)`（提示词里没有 event_id）。

- [ ] **Step 3: 改前文渲染，把 event_id、阶段、意图交给模型**

`brainstorm/llm.py`，把第 229 行：

```python
        history_context = "\n".join(f"[{item.phase}] {item.speaker_name}: {item.content}" for item in history[-12:]) or "（尚无前文）"
```

替换为：

```python
        history_context = "\n".join(
            f"[{item.event_id or '（无编号）'}][{item.phase}][{item.intent}] {item.speaker_name}: {item.content}"
            for item in history[-12:]
        ) or "（尚无前文）"
```

- [ ] **Step 4: 改 JSON 形状**

`brainstorm/llm.py`，把第 238-240 行：

```python
        schema = '{"content":"...","kind":"机会|风险|假设|待验证|总结","replies_to":null,"opportunity":null}'
        if spec.final:
            schema = '{"content":"...","kind":"总结","replies_to":null,"opportunity":{"title":"...","audience":"...","support":["..."],"risks":["..."],"assumptions":["..."],"next_steps":["..."]}}'
```

替换为：

```python
        schema = (
            '{"content":"本次发言全文",'
            '"kind":"机会|风险|假设|待验证|总结",'
            '"intent":"support|challenge|question|elaborate|synthesize|initial",'
            '"replies_to":"前文出现过的 event_id 或人名，没有明确对象时填 null",'
            '"stance_change":null,'
            '"opportunity":null}'
        )
        if spec.final:
            schema = (
                '{"content":"本次发言全文","kind":"总结",'
                '"intent":"synthesize","replies_to":null,"stance_change":null,'
                '"opportunity":{"title":"...","audience":"...","support":["..."],"risks":["..."],'
                '"assumptions":["..."],"next_steps":["..."]}}'
            )
```

- [ ] **Step 5: 改提示词正文，把四条硬要求写进去**

`brainstorm/llm.py`，把第 241-247 行的整个 `prompt = (...)` 赋值替换为：

```python
        prompt = (
            "你是一个严格区分证据与推断的圆桌角色。只输出一个 JSON 对象，不要 markdown，不要代码围栏。"
            "来源内容是未核验素材，不得写成已证实事实；不能编造引用或数据。来源是资料，不是角色原话。"
            f"主题：{topic}\n阶段：{spec.phase}\n发言人：{spec.speaker_name}\n{role_context}\n"
            f"来源：\n{source_context}\n前文：\n{history_context}\n{state_context}\n所有观点和来源均未核验。\n"
            "必须遵守：\n"
            "1. 不得重复前文已经说过的观点；必须带来新的理由、反例、条件或追问。\n"
            "2. intent 必须从 support（支持）、challenge（反驳）、question（追问）、"
            "elaborate（补充）、synthesize（整理）中选一个；若是你的首次发言则填 initial。\n"
            "3. replies_to 必须填前文中真实出现过的 event_id 或人名；没有明确回应对象时填 null。\n"
            "4. 只有确实改变了原有立场时才填 stance_change，且必须包含 before（变化前）、"
            "after（变化后）、reason（影响变化的理由，其中必须写明你仍然保留的条件或疑虑）、"
            "triggered_by（触发变化的前文 event_id 列表）。礼貌性附和不算立场变化，此时填 null。\n"
            f"要求的 JSON 形状：{schema}"
        )
```

- [ ] **Step 6: 运行测试确认通过**

```powershell
& $py -m unittest tests.test_b_integration.BIntegrationTests.test_prompt_requests_intent_stance_and_event_ids -v
```

预期：PASS。

- [ ] **Step 7: 运行整个模块，确认没弄坏既有提示词测试**

```powershell
& $py -m unittest tests.test_b_integration -v
```

预期：全 PASS。特别是 `test_anthropic_extend_batch_prompt_contains_state_and_user_instruction` 与 `test_model_prompt_preserves_news_link_date_and_source_type` 仍通过（提示词里仍然含有插话文本、"未核验"、来源链接、日期与 `rss`）。

- [ ] **Step 8: 提交**

```powershell
git add brainstorm/llm.py tests/test_b_integration.py
git commit -m "feat: prompt requests intent, stance_change and event ids"
```

---

## Task 2: 按人名回指时取最新一条，而不是最早一条

`llm.py:328` 用 `next(... for item in history ...)`，取到的是该角色**最早**一条发言。角色多次发言后，回应最新观点会被挂到旧发言上。现有测试 `test_anthropic_parse_converts_speaker_reply_reference_to_event_id`（`tests/test_b_integration.py:70`）只有一条前文，所以这个 bug 从未被测出。

**Files:**
- Modify: `brainstorm/llm.py:328`
- Test: `tests/test_b_integration.py`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_b_integration.py` 的 `BIntegrationTests` 类内：

```python
    def test_speaker_reply_reference_resolves_to_latest_utterance(self):
        spec = TurnSpec("r", "角色", "动态交锋")
        prior = [
            Utterance("other", "另一角色", "第一次发言", ViewpointKind.OPPORTUNITY, "独立观点", event_id="event-000001", sequence=1),
            Utterance("other", "另一角色", "第二次发言", ViewpointKind.RISK, "动态交锋", event_id="event-000002", sequence=2),
        ]
        payload = '{"content":"我回应你最新的质疑","replies_to":"另一角色","intent":"challenge"}'
        utterance, _ = AnthropicDiscussionProvider._parse(payload, spec, prior)
        self.assertEqual(utterance.replies_to, "event-000002")
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
& $py -m unittest tests.test_b_integration.BIntegrationTests.test_speaker_reply_reference_resolves_to_latest_utterance -v
```

预期：FAIL，`AssertionError: 'event-000001' != 'event-000002'`。

- [ ] **Step 3: 改为从后往前找**

`brainstorm/llm.py`，把第 328 行：

```python
            replies_to = next((item.event_id for item in history if item.event_id == replies_to or item.speaker_id == replies_to), replies_to)
```

替换为：

```python
            replies_to = next(
                (item.event_id for item in reversed(history) if item.event_id == replies_to or item.speaker_id == replies_to),
                replies_to,
            )
```

- [ ] **Step 4: 运行测试确认通过**

```powershell
& $py -m unittest tests.test_b_integration.BIntegrationTests.test_speaker_reply_reference_resolves_to_latest_utterance -v
```

预期：PASS。

- [ ] **Step 5: 提交**

```powershell
git add brainstorm/llm.py tests/test_b_integration.py
git commit -m "fix: resolve speaker reply reference to the latest utterance"
```

---

## Task 3: 统一剥离 markdown 代码围栏

OpenAI 兼容路径会剥代码围栏（`llm.py:419-420`），Anthropic 路径不会。模型习惯性输出 ```json 时，Anthropic 路径直接解析失败并回退离线。把该处理下沉为公共函数，两条路径共用。

**Files:**
- Modify: `brainstorm/llm.py`（新增模块级函数；`_parse` 入口；OpenAI `_request` 改为调用它）
- Test: `tests/test_b_integration.py`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_b_integration.py` 的 `BIntegrationTests` 类内：

```python
    def test_parse_strips_markdown_code_fence(self):
        spec = TurnSpec("r", "角色", "动态交锋")
        payload = '```json\n{"content":"围栏内的观点","kind":"机会","intent":"support"}\n```'
        utterance, _ = AnthropicDiscussionProvider._parse(payload, spec, [])
        self.assertEqual(utterance.content, "围栏内的观点")
        self.assertEqual(utterance.intent, "support")
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
& $py -m unittest tests.test_b_integration.BIntegrationTests.test_parse_strips_markdown_code_fence -v
```

预期：FAIL，抛出 `ProviderFailure`（`code == "malformed_json"`）。

- [ ] **Step 3: 新增公共函数**

`brainstorm/llm.py`，在 `ProviderFailure` 类定义之前插入：

```python
def _strip_code_fence(text: str) -> str:
    """Remove a surrounding markdown code fence that models add habitually.

    Tolerates a language tag (```` ```json ````) and a trailing fence.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    if body.rstrip().endswith("```"):
        body = body.rstrip()[:-3]
    return body.strip()
```

- [ ] **Step 4: 在解析入口使用它**

`brainstorm/llm.py`，把 `_parse` 里的第 308 行：

```python
            data = json.loads(text)
```

替换为：

```python
            data = json.loads(_strip_code_fence(text))
```

- [ ] **Step 5: OpenAI 路径改为共用同一函数（去重）**

`brainstorm/llm.py`，把 OpenAI `_request` 里的第 419-420 行：

```python
                if text.startswith('```') and text.endswith('```'):
                    text = text.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
```

替换为：

```python
                text = _strip_code_fence(text)
```

- [ ] **Step 6: 运行测试确认通过**

```powershell
& $py -m unittest tests.test_b_integration -v
```

预期：全 PASS，包含新增的围栏测试与原有的 `test_openai_compatible_provider_parses_chat_completion`。

- [ ] **Step 7: 提交**

```powershell
git add brainstorm/llm.py tests/test_b_integration.py
git commit -m "fix: strip markdown code fences on every provider path"
```

---

## Task 4: 新建本地调度器，用结构事实取代按名册轮转

这是第二期的核心。新模块只回答事件流能精确回答的问题，**不做语义相关性判断**（谁最合适回答由第三期的编排层决定）。

**Files:**
- Create: `brainstorm/turn_planner.py`
- Test: `tests/test_turn_planner.py`

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_turn_planner.py`：

```python
import unittest

from brainstorm.models import DiscussionSession, DiscussionState, Role, StanceChange, Utterance, ViewpointKind
from brainstorm.turn_planner import TurnPlan, detect_intervention, plan_turn


ROLES = [
    Role("trend", "趋势分析师", "辨别变化", "#2563eb", "关注变化是否真实。"),
    Role("builder", "创业实践者", "把机会转成产品", "#7c3aed", "关注谁付费。"),
    Role("skeptic", "怀疑者", "寻找伪需求", "#dc2626", "主动寻找反例。"),
]


def build(*utterances):
    session = DiscussionSession(topic="社区养老", selected_role_ids=[role.id for role in ROLES])
    for item in utterances:
        session.append_utterance(item)
    return session


def say(speaker_id, speaker_name, content, kind=ViewpointKind.ASSUMPTION, phase="动态交锋",
        intent="initial", replies_to=None, moderator=False):
    return Utterance(
        speaker_id if not moderator else "moderator",
        speaker_name, content, kind, phase,
        replies_to=replies_to, origin="model", intent=intent,
    )


class TurnPlannerTests(unittest.TestCase):
    def test_user_interjection_is_answered_first(self):
        session = build(
            say("trend", "趋势分析师", "开场观点"),
            say("user", "用户", "先讨论无障碍体验", intent="user_instruction"),
        )
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertEqual(plan.reason, "你刚才插话，优先回应")
        self.assertEqual(plan.reply_to_event_id, session.utterances[-1].event_id)
        self.assertNotEqual(plan.speaker_id, "user")

    def test_interjection_is_not_repeated_once_answered(self):
        session = build(
            say("user", "用户", "先讨论无障碍体验", intent="user_instruction"),
            say("trend", "趋势分析师", "我先回应插话", intent="elaborate", replies_to="event-000000"),
        )
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertNotEqual(plan.reason, "你刚才插话，优先回应")

    def test_unanswered_question_is_routed_to_another_role(self):
        session = build(
            say("trend", "趋势分析师", "现有观点"),
            say("skeptic", "怀疑者", "第一批用户为什么不用现成的？", phase="回应", intent="question", replies_to="event-000000"),
        )
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertIn("提问还没有人回答", plan.reason)
        self.assertEqual(plan.reply_to_event_id, session.utterances[-1].event_id)
        self.assertNotEqual(plan.speaker_id, "skeptic")

    def test_challenged_role_that_has_not_replied_speaks_next(self):
        session = build(
            say("builder", "创业实践者", "先做小范围试点"),
            say("skeptic", "怀疑者", "没有和现有替代方案比较", intent="challenge", replies_to="event-000000"),
        )
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertEqual(plan.speaker_id, "builder")
        self.assertEqual(plan.reply_to_event_id, session.utterances[-1].event_id)
        self.assertIn("质疑尚未回应", plan.reason)

    def test_role_is_not_reused_when_it_already_replied(self):
        session = build(
            say("builder", "创业实践者", "先做小范围试点"),
            say("skeptic", "怀疑者", "没有和现有替代方案比较", intent="challenge", replies_to="event-000000"),
            say("builder", "创业实践者", "我补充对比数据", phase="正面反驳", intent="challenge", replies_to="event-000001"),
        )
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertNotEqual(plan.speaker_id, "builder")

    def test_silent_role_is_brought_back(self):
        session = build(
            say("trend", "趋势分析师", "一"),
            say("builder", "创业实践者", "二"),
            say("builder", "创业实践者", "三"),
            say("builder", "创业实践者", "四"),
        )
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertEqual(plan.speaker_id, "trend")
        self.assertIn("加入交锋", plan.reason)

    def test_same_speaker_never_exceeds_two_consecutive_turns(self):
        session = build(
            say("trend", "趋势分析师", "一"),
            say("builder", "创业实践者", "二"),
            say("builder", "创业实践者", "三"),
        )
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertNotEqual(plan.speaker_id, "builder")

    def test_plan_is_produced_without_any_history(self):
        session = build()
        plan = plan_turn(session, ROLES, DiscussionState())
        self.assertIn(plan.speaker_id, {role.id for role in ROLES})
        self.assertEqual(plan.reason, "补充已有观点")

    def test_roles_are_recovered_from_history_when_none_are_passed(self):
        session = build(say("trend", "趋势分析师", "一"))
        plan = plan_turn(session, [], DiscussionState())
        self.assertEqual(plan.speaker_id, "trend")
        self.assertEqual(plan.speaker_name, "趋势分析师")
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
& $py -m unittest tests.test_turn_planner -v
```

预期：`ModuleNotFoundError: No module named 'brainstorm.turn_planner'`。

- [ ] **Step 3: 写出最小实现**

创建 `brainstorm/turn_planner.py`：

```python
"""Local, network-free structural analysis for speaker scheduling.

This module answers only what the recorded event stream can answer exactly:
who owes a reply, which question is still unanswered, who has been silent too
long.  It deliberately does NOT judge semantic relevance -- deciding who is
best placed to answer belongs to the model-driven orchestrator.  Its output is
therefore both an input to that orchestrator and the fallback plan used when
the model is unavailable or suggests an impossible speaker.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from .models import DiscussionSession, DiscussionState, Role, Utterance

MODERATOR_ID = "moderator"
USER_ID = "user"

# Bounds keep every rule local and cheap: a stale interjection or a very old
# question must not steer the discussion forever.
USER_WINDOW = 6
QUESTION_WINDOW = 12
MAX_SILENT_TURNS = 3
MAX_CONSECUTIVE_SAME_SPEAKER = 2


@dataclass(frozen=True)
class TurnPlan:
    """One scheduled turn. ``reason`` is always a real local trigger, never text."""

    speaker_id: str
    speaker_name: str
    phase: str
    intent: str
    kind_hint: str = "假设"
    reply_to_event_id: str | None = None
    reason: str = ""
    moderator: bool = False
    intervention_reason: str = ""
    source: str = "local"


def _role_utterances(session: DiscussionSession) -> list[Utterance]:
    return [item for item in session.utterances if item.speaker_id not in {MODERATOR_ID, USER_ID}]


def _replied_ids(session: DiscussionSession) -> set[str]:
    return {item.replies_to for item in _role_utterances(session) if item.replies_to}


def _speaker_counts(session: DiscussionSession) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in _role_utterances(session):
        counts[item.speaker_id] = counts.get(item.speaker_id, 0) + 1
    return counts


def _last_index(session: DiscussionSession, speaker_id: str) -> int:
    for index in range(len(session.utterances) - 1, -1, -1):
        if session.utterances[index].speaker_id == speaker_id:
            return index
    return -1


def _turns_since_spoke(session: DiscussionSession, speaker_id: str) -> int:
    last = _last_index(session, speaker_id)
    if last < 0:
        return len(session.utterances) + 1
    return sum(1 for item in session.utterances[last + 1:] if item.speaker_id not in {MODERATOR_ID, USER_ID})


def _least_spoken(candidates: Sequence[Role], session: DiscussionSession, exclude: Sequence[str] = ()) -> Role | None:
    """Fewest utterances first; ties broken by who spoke longest ago."""
    blocked = set(exclude)
    pool = [role for role in candidates if role.id not in blocked]
    if not pool:
        return None
    counts = _speaker_counts(session)
    return min(pool, key=lambda role: (counts.get(role.id, 0), _last_index(session, role.id)))


def _role_by_reference(candidates: Sequence[Role], session: DiscussionSession, reference: str | None) -> Role | None:
    """Accept either an event_id or a bare speaker_id."""
    if not reference:
        return None
    speaker_id = next((item.speaker_id for item in session.utterances if item.event_id == reference), None)
    if speaker_id is None:
        speaker_id = next((item.speaker_id for item in session.utterances if item.speaker_id == reference), None)
    return next((role for role in candidates if role.id == speaker_id), None)


def _roles_from_history(session: DiscussionSession) -> list[Role]:
    found: dict[str, str] = {}
    for item in session.utterances:
        if item.speaker_id in {MODERATOR_ID, USER_ID}:
            continue
        found.setdefault(item.speaker_id, item.speaker_name)
    return [Role(role_id, name, "", "#b08d50", "") for role_id, name in found.items()]


def detect_intervention(session: DiscussionSession, recent: int = 6) -> tuple[bool, str]:
    """Decide whether the host should summarize, from structural evidence only.

    The five reasons mirror the approved protocol: a disagreement that has been
    fully argued, an important consensus, rising repetition, a stalled
    discussion, or a falling rate of new points.
    """
    recent_items = _role_utterances(session)[-recent:]
    if len(recent_items) < recent:
        return False, ""
    challenged = [item.replies_to for item in recent_items if item.intent == "challenge" and item.replies_to]
    if any(challenged.count(target) >= 3 for target in set(challenged)) and any(item.stance_change for item in recent_items):
        return True, "关键分歧已经充分交锋，需要主持人收束"
    supported = [item.replies_to for item in recent_items if item.intent == "support" and item.replies_to]
    if any(supported.count(target) >= 3 for target in set(supported)):
        return True, "已出现重要共识，需要主持人确认"
    duplicates = sum(1 for item in recent_items if item.duplicate)
    if duplicates >= 2:
        return True, "重复观点增加，需要主持人整理"
    if len({item.speaker_id for item in recent_items}) <= 2:
        return True, "发言集中在少数角色，讨论冷场"
    # Content-based, so this trigger works today -- before phase 4 starts
    # setting the duplicate flag. The flag-based check above only becomes live
    # once duplicate detection exists, and the two stay independently reachable.
    if len({item.content.strip() for item in recent_items}) <= len(recent_items) - 2:
        return True, "新观点减少，需要主持人整理"
    return False, ""


def plan_turn(
    session: DiscussionSession,
    roles: Sequence[Role],
    state: DiscussionState | None = None,
) -> TurnPlan:
    """Return the next turn to generate, using local structure only."""
    candidates = [role for role in roles if role.id != MODERATOR_ID]
    if not candidates:
        candidates = _roles_from_history(session)
    if not candidates:
        return TurnPlan(
            MODERATOR_ID, "主持人", "阶段总结", "synthesize", "总结",
            reason="尚无可发言的角色", moderator=True,
        )

    should_intervene, intervention_reason = detect_intervention(session)
    if should_intervene:
        return TurnPlan(
            MODERATOR_ID, "主持人", "状态整理", "synthesize", "总结",
            reason=intervention_reason, moderator=True, intervention_reason=intervention_reason,
        )

    replied = _replied_ids(session)

    # Rule 1: an unanswered user interjection outranks everything else.
    interjection = next(
        (item for item in reversed(session.utterances[-USER_WINDOW:]) if item.speaker_id == USER_ID),
        None,
    )
    if interjection is not None and interjection.event_id not in replied:
        speaker = _least_spoken(candidates, session)
        if speaker is not None:
            return _guard(TurnPlan(
                speaker.id, speaker.name, "回应插话", "elaborate", "假设",
                reply_to_event_id=interjection.event_id,
                reason="你刚才插话，优先回应",
            ), session, candidates)

    # Rule 2: a question nobody answered.
    questions = [
        item for item in _role_utterances(session)[-QUESTION_WINDOW:]
        if item.intent == "question" and item.event_id not in replied
    ]
    if questions:
        question = questions[-1]
        speaker = _role_by_reference(candidates, session, question.replies_to) or _least_spoken(
            candidates, session, exclude=[question.speaker_id]
        )
        if speaker is not None:
            return _guard(TurnPlan(
                speaker.id, speaker.name, "回答提问", "elaborate", "待验证",
                reply_to_event_id=question.event_id,
                reason=f"{question.speaker_name}的提问还没有人回答",
            ), session, candidates)

    # Rule 3: somebody was challenged and has not spoken since.
    owed: list[tuple[Utterance, Role]] = []
    for index, item in enumerate(session.utterances):
        if item.intent != "challenge" or not item.replies_to:
            continue
        target = _role_by_reference(candidates, session, item.replies_to)
        if target is None or target.id == item.speaker_id:
            continue
        if not any(later.speaker_id == target.id for later in session.utterances[index + 1:]):
            owed.append((item, target))
    if owed:
        challenge, target = owed[-1]
        return _guard(TurnPlan(
            target.id, target.name, "正面反驳", "challenge", "风险",
            reply_to_event_id=challenge.event_id,
            reason=f"{challenge.speaker_name}的质疑尚未回应",
        ), session, candidates)

    # Rule 4: bring back whoever has been silent longest.
    silent = [role for role in candidates if _turns_since_spoke(session, role.id) >= MAX_SILENT_TURNS]
    if silent:
        speaker = _least_spoken(silent, session)
        if speaker is not None:
            return _guard(TurnPlan(
                speaker.id, speaker.name, "补充观点", "elaborate", "假设",
                reason=f"让 {speaker.name} 加入交锋",
            ), session, candidates)

    # Rule 5: fallback -- fewest turns, then longest silent.
    speaker = _least_spoken(candidates, session)
    assert speaker is not None  # candidates is non-empty here
    return _guard(TurnPlan(
        speaker.id, speaker.name, "回应", "elaborate", "假设",
        reason="补充已有观点",
    ), session, candidates)


def _guard(plan: TurnPlan, session: DiscussionSession, candidates: Sequence[Role]) -> TurnPlan:
    """Never let one role take three turns in a row."""
    recent = [item.speaker_id for item in _role_utterances(session)][-MAX_CONSECUTIVE_SAME_SPEAKER:]
    if len(recent) == MAX_CONSECUTIVE_SAME_SPEAKER and all(speaker_id == plan.speaker_id for speaker_id in recent):
        alternative = _least_spoken(candidates, session, exclude=[plan.speaker_id])
        if alternative is not None:
            return replace(
                plan,
                speaker_id=alternative.id,
                speaker_name=alternative.name,
                reason=f"{plan.reason}（避免同一角色连续发言）",
            )
    return plan
```

- [ ] **Step 4: 运行测试确认通过**

```powershell
& $py -m unittest tests.test_turn_planner -v
```

预期：全 PASS（9 项）。

若 `test_silent_role_is_brought_back` 失败：检查 `_turns_since_spoke` 是否把 moderator/user 也计入了尾随条数——它只应统计角色发言。

- [ ] **Step 5: 提交**

```powershell
git add brainstorm/turn_planner.py tests/test_turn_planner.py
git commit -m "feat: add local turn planner driven by structural facts"
```

---

## Task 5: 介入检测的五个触发条件各自可测

`detect_intervention` 已在 Task 4 写出，但只被间接覆盖。协议 §2.1 的五个触发条件必须各自有一条测试，否则将来改坏任何一个都不会被发现。

**Files:**
- Test: `tests/test_turn_planner.py`

- [ ] **Step 1: 追加测试**

追加到 `tests/test_turn_planner.py` 的 `TurnPlannerTests` 类内：

```python
    def test_intervention_on_fully_argued_disagreement(self):
        session = DiscussionSession(topic="社区养老", selected_role_ids=["builder", "skeptic", "trend"])
        session.append_utterance(say("builder", "创业实践者", "方案"))
        session.append_utterance(say("skeptic", "怀疑者", "反例一", intent="challenge", replies_to="event-000000"))
        session.append_utterance(say("skeptic", "怀疑者", "反例二", intent="challenge", replies_to="event-000000"))
        session.append_utterance(say("skeptic", "怀疑者", "反例三", intent="challenge", replies_to="event-000000"))
        session.append_utterance(Utterance(
            "builder", "创业实践者", "我缩小验证范围", ViewpointKind.OPPORTUNITY, "正面反驳",
            replies_to="event-000000", origin="model", intent="support",
            stance_change=StanceChange("坚持原方案", "缩小验证范围", "被反例说服，但仍保留成本疑虑"),
        ))
        session.append_utterance(say("trend", "趋势分析师", "我补充一个角度"))
        triggered, reason = detect_intervention(session)
        self.assertTrue(triggered)
        self.assertEqual(reason, "关键分歧已经充分交锋，需要主持人收束")

    def test_intervention_on_important_consensus(self):
        session = build(
            say("trend", "趋势分析师", "目标"),
            say("builder", "创业实践者", "同意一", intent="support", replies_to="event-000000"),
            say("skeptic", "怀疑者", "同意二", intent="support", replies_to="event-000000"),
            say("builder", "创业实践者", "同意三", intent="support", replies_to="event-000000"),
            say("skeptic", "怀疑者", "另一个角度"),
            say("trend", "趋势分析师", "再补充一点"),
        )
        triggered, reason = detect_intervention(session)
        self.assertTrue(triggered)
        self.assertEqual(reason, "已出现重要共识，需要主持人确认")

    def test_intervention_on_rising_duplicates(self):
        session = build(
            say("trend", "趋势分析师", "一"),
            say("builder", "创业实践者", "二"),
            say("skeptic", "怀疑者", "三"),
            say("trend", "趋势分析师", "四"),
            say("builder", "创业实践者", "五", duplicate=True),
            say("skeptic", "怀疑者", "六", duplicate=True),
        )
        triggered, reason = detect_intervention(session)
        self.assertTrue(triggered)
        self.assertEqual(reason, "重复观点增加，需要主持人整理")

    def test_intervention_on_stalled_discussion(self):
        session = build(
            say("trend", "趋势分析师", "一"),
            say("builder", "创业实践者", "二"),
            say("trend", "趋势分析师", "三"),
            say("builder", "创业实践者", "四"),
            say("trend", "趋势分析师", "五"),
            say("builder", "创业实践者", "六"),
        )
        triggered, reason = detect_intervention(session)
        self.assertTrue(triggered)
        self.assertEqual(reason, "发言集中在少数角色，讨论冷场")

    def test_intervention_on_falling_new_information(self):
        # Duplicate flags are not set yet (phase 4 introduces them), so this
        # exercises the content-based branch: three distinct speakers, but only
        # four distinct things said across six turns.
        session = build(
            say("trend", "趋势分析师", "一"),
            say("trend", "趋势分析师", "一"),
            say("builder", "创业实践者", "二"),
            say("builder", "创业实践者", "二"),
            say("skeptic", "怀疑者", "三"),
            say("trend", "趋势分析师", "四"),
        )
        triggered, reason = detect_intervention(session)
        self.assertTrue(triggered)
        self.assertEqual(reason, "新观点减少，需要主持人整理")

    def test_no_intervention_on_short_or_healthy_history(self):
        short = build(say("trend", "趋势分析师", "一"))
        self.assertEqual(detect_intervention(short), (False, ""))
        healthy = build(
            say("trend", "趋势分析师", "一"),
            say("builder", "创业实践者", "我反对这个前提", intent="challenge", replies_to="event-000000"),
            say("skeptic", "怀疑者", "我追问证据", intent="question", replies_to="event-000001"),
            say("trend", "趋势分析师", "我补充数据", intent="elaborate", replies_to="event-000002"),
            say("builder", "创业实践者", "我调整范围", phase="正面反驳", intent="support", replies_to="event-000002"),
            say("skeptic", "怀疑者", "我保留疑虑", intent="question"),
        )
        self.assertEqual(detect_intervention(healthy), (False, ""))
```

- [ ] **Step 2: 运行测试**

```powershell
& $py -m unittest tests.test_turn_planner -v
```

预期：全 PASS（15 项）。

五个触发条件各自命中不同分支，互不遮挡：`fully_argued` 走反驳计数、`important_consensus` 走支持计数、`rising_duplicates` 走重复标记、`stalled` 走发言人数量、`falling_new_information` 走内容去重。若 `falling_new_information` 报出了别的理由，说明前四条分支的判定条件被写松了，回去收紧实现，**不要修改测试期望**。

- [ ] **Step 3: 提交**

```powershell
git add tests/test_turn_planner.py
git commit -m "test: cover the five protocol intervention triggers"
```

---

## Task 6: `extend_batch` 接入调度器，并把编排要求写进提示词

**Files:**
- Modify: `brainstorm/llm.py:178-203`（`extend_batch`）、`brainstorm/llm.py:205-252`（`generate_turn` 增加 `plan` 形参）
- Test: `tests/test_b_integration.py`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_b_integration.py` 的 `BIntegrationTests` 类内：

```python
    def test_extend_batch_picks_the_challenged_role(self):
        captured = []

        class Event:
            text = '{"content":"我回应质疑","intent":"challenge"}'

        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])

        class Messages:
            def stream(self, **kwargs):
                captured.append(kwargs["messages"][0]["content"])
                return Stream()

        class Client:
            messages = Messages()

        provider = AnthropicDiscussionProvider(client=Client(), model="test-model")
        session = DiscussionSession(topic="社区养老", selected_role_ids=["builder", "skeptic"])
        session.append_utterance(Utterance("builder", "创业实践者", "先做小试点", ViewpointKind.OPPORTUNITY, "独立观点", origin="model"))
        session.append_utterance(Utterance("skeptic", "怀疑者", "没和现有替代方案比", ViewpointKind.RISK, "动态交锋",
                                          replies_to="event-000000", origin="model", intent="challenge"))
        roles = [
            Role("builder", "创业实践者", "把机会转成产品", "#7c3aed", "关注谁付费。"),
            Role("skeptic", "怀疑者", "寻找伪需求", "#dc2626", "主动寻找反例。"),
        ]
        added = provider.extend_batch(session, DiscussionState(), roles=roles)
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0].speaker_id, "builder")
        self.assertIn("创业实践者", captured[0])
        self.assertIn("质疑尚未回应", captured[0])

    def test_extend_batch_inserts_moderator_when_intervention_triggers(self):
        class Event:
            text = '{"content":"本阶段整理","kind":"总结","intent":"synthesize"}'

        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])

        class Messages:
            def stream(self, **_): return Stream()

        class Client:
            messages = Messages()

        provider = AnthropicDiscussionProvider(client=Client(), model="test-model")
        session = DiscussionSession(topic="社区养老", selected_role_ids=["trend", "builder"])
        for index in range(6):
            session.append_utterance(Utterance(
                "trend" if index % 2 == 0 else "builder",
                "趋势分析师" if index % 2 == 0 else "创业实践者",
                f"第{index}条", ViewpointKind.ASSUMPTION, "动态交锋", origin="model",
            ))
        roles = [
            Role("trend", "趋势分析师", "辨别变化", "#2563eb", "关注变化。"),
            Role("builder", "创业实践者", "把机会转成产品", "#7c3aed", "关注谁付费。"),
        ]
        added = provider.extend_batch(session, DiscussionState(), roles=roles)
        self.assertEqual(added[0].speaker_id, "moderator")
        self.assertEqual(added[0].phase, "状态整理")
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
& $py -m unittest tests.test_b_integration.BIntegrationTests.test_extend_batch_picks_the_challenged_role -v
```

预期：FAIL。当前实现按 `continuations % len(participants)` 轮转，`continuations` 为 1（一条 `动态交锋` 的模型发言），`participants` 长度为 2，所以选中 `skeptic` 而不是 `builder`。

- [ ] **Step 3: 改 `extend_batch`**

`brainstorm/llm.py`，在文件顶部 import 区加入：

```python
from .turn_planner import TurnPlan, plan_turn
```

把 `extend_batch` 的方法体（第 187-203 行）从：

```python
        selected = list(roles)
        participants = [role for role in selected if role.id != "moderator"]
        continuations = sum(item.phase == "动态交锋" and item.origin == "model" for item in session.utterances)
        speaker = participants[continuations % len(participants)] if participants else None
        if speaker is None:
            speaker = Role("moderator", "主持人", "编排、收敛和标记不确定性", "#b08d50", "整理当前讨论")
        result = self.generate_turn(
            session.topic,
            selected,
            list(session.sources),
            list(session.utterances),
            TurnSpec(speaker.id, speaker.name, "动态交锋", "假设"),
            on_partial=(lambda text: on_partial(speaker.name, text)) if on_partial else None,
            cancel_event=cancel_event,
            state=state,
        )
        return [result.utterance]
```

替换为：

```python
        selected = list(roles)
        plan = plan_turn(session, selected, state)
        speaker = next((role for role in selected if role.id == plan.speaker_id), None)
        if speaker is None:
            speaker = Role(plan.speaker_id, plan.speaker_name, "编排、收敛和标记不确定性", "#b08d50", "整理当前讨论")
        result = self.generate_turn(
            session.topic,
            selected,
            list(session.sources),
            list(session.utterances),
            TurnSpec(plan.speaker_id, plan.speaker_name, plan.phase, plan.kind_hint),
            on_partial=(lambda text: on_partial(speaker.name, text)) if on_partial else None,
            cancel_event=cancel_event,
            state=state,
            plan=plan,
        )
        return [result.utterance]
```

- [ ] **Step 4: 给 `generate_turn` 增加 `plan` 形参并写入提示词**

`brainstorm/llm.py`，把 `generate_turn` 的签名（第 205-216 行）中的：

```python
        state: DiscussionState | None = None,
    ) -> TurnResult:
```

替换为：

```python
        state: DiscussionState | None = None,
        plan: TurnPlan | None = None,
    ) -> TurnResult:
```

然后在该方法的 `response = self._request(...)` 之前（即 `prompt = (...)` 赋值之后）插入：

```python
        if plan is not None and plan.moderator:
            prompt += (
                f"\n本次是主持人的状态整理发言，介入原因：「{plan.intervention_reason}」。"
                "请只整理已经发生的观点，不要提出新的主张。\n"
            )
        elif plan is not None:
            target = next(
                (f"[{item.event_id}] {item.speaker_name}" for item in reversed(history) if item.event_id == plan.reply_to_event_id),
                "前文尚未解决的重点",
            )
            prompt += (
                f"\n本地编排要求：本次发言必须回应 {target}；依据是「{plan.reason}」。"
                "若你认为该对象不合适，可以改选回应对象，但必须在 intent 中如实表达。\n"
            )
```

- [ ] **Step 5: 运行两个新测试**

```powershell
& $py -m unittest tests.test_b_integration.BIntegrationTests.test_extend_batch_picks_the_challenged_role tests.test_b_integration.BIntegrationTests.test_extend_batch_inserts_moderator_when_intervention_triggers -v
```

预期：两条都 PASS。

- [ ] **Step 6: 运行相关模块，检查既有行为**

```powershell
& $py -m unittest tests.test_b_integration tests.test_generation_controller tests.test_openai_settings tests.test_turn_planner -v
```

预期：全 PASS。注意 `test_anthropic_extend_batch_prompt_contains_state_and_user_instruction` 仍在——新实现会走调度器规则 1（插话未被回应），提示词里仍含插话文本与"未核验"。

- [ ] **Step 7: 提交**

```powershell
git add brainstorm/llm.py tests/test_b_integration.py
git commit -m "feat: schedule turns from structural facts instead of roster order"
```

---

## Task 7: 在控制器里记录主持人介入原因

`host_intervention_reason` 会被持久化（`storage.py:80`）但模型路径从不写它。在 `_apply_batch` 里于主场线程用同一个本地函数算出，避免跨线程改状态。

**Files:**
- Modify: `brainstorm/session_controller.py:497-514`（`_apply_batch`）
- Test: `tests/test_generation_controller.py`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_generation_controller.py` 的 `GenerationControllerTests` 类内：

```python
    def test_moderator_batch_records_intervention_reason(self):
        from brainstorm.models import DiscussionSession, Utterance, ViewpointKind
        from brainstorm.session_controller import SessionController
        from brainstorm.turn_planner import detect_intervention

        controller = SessionController()
        session = DiscussionSession(topic="社区养老", selected_role_ids=["trend", "builder"])
        for index in range(6):
            session.append_utterance(Utterance(
                "trend" if index % 2 == 0 else "builder",
                "趋势分析师" if index % 2 == 0 else "创业实践者",
                f"第{index}条", ViewpointKind.ASSUMPTION, "动态交锋", origin="model",
            ))
        controller.playback.live = True
        controller.playback.start(session)
        controller._apply_batch([Utterance(
            "moderator", "主持人", "本阶段整理", ViewpointKind.SUMMARY, "状态整理",
            origin="model", intent="synthesize",
        )])
        expected = detect_intervention(session)[1]
        self.assertTrue(expected)
        self.assertEqual(session.discussion_state.host_intervention_reason, expected)

    def test_role_batch_clears_stale_intervention_reason(self):
        from brainstorm.models import DiscussionSession, Utterance, ViewpointKind
        from brainstorm.session_controller import SessionController

        controller = SessionController()
        session = DiscussionSession(topic="社区养老", selected_role_ids=["trend"])
        session.append_utterance(Utterance("trend", "趋势分析师", "开场", ViewpointKind.ASSUMPTION, "独立观点", origin="model"))
        session.discussion_state.host_intervention_reason = "上一次介入"
        controller.playback.live = True
        controller.playback.start(session)
        controller._apply_batch([Utterance("trend", "趋势分析师", "继续", ViewpointKind.ASSUMPTION, "动态交锋", origin="model")])
        self.assertEqual(session.discussion_state.host_intervention_reason, "")
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
& $py -m unittest tests.test_generation_controller.GenerationControllerTests.test_moderator_batch_records_intervention_reason tests.test_generation_controller.GenerationControllerTests.test_role_batch_clears_stale_intervention_reason -v
```

预期：两条都 FAIL（`host_intervention_reason` 仍是空字符串 / 仍是"上一次介入"）。

- [ ] **Step 3: 改 `_apply_batch`**

`brainstorm/session_controller.py`，在 import 区加入：

```python
from .turn_planner import detect_intervention
```

把 `_apply_batch`（第 497-514 行）中的：

```python
        for item in items:
            self.session.append_utterance(item)
            self.store.save(self.session)
        self.session.rebuild_state()
        self.store.save(self.session)
```

替换为：

```python
        for item in items:
            self.session.append_utterance(item)
            self.store.save(self.session)
        self.session.rebuild_state()
        if any(item.speaker_id == "moderator" and item.phase == "状态整理" for item in items):
            self.session.discussion_state.host_intervention_reason = detect_intervention(self.session)[1]
        elif any(item.speaker_id != "moderator" for item in items):
            self.session.discussion_state.host_intervention_reason = ""
        self.store.save(self.session)
```

- [ ] **Step 4: 运行测试确认通过**

```powershell
& $py -m unittest tests.test_generation_controller -v
```

预期：全 PASS。

- [ ] **Step 5: 提交**

```powershell
git add brainstorm/session_controller.py tests/test_generation_controller.py
git commit -m "feat: record the moderator intervention reason on model turns"
```

---

## Task 8: 界面显示回应对象与介入原因

协议 §5 要求"每条记录显示回应对象"与"主持人整理显示介入原因"，两者当前都没实现。

**Files:**
- Modify: `brainstorm/qt_app.py:599-619`（`_utterance`、`_show_current_text`）
- Test: `tests/test_qt_ui.py`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_qt_ui.py` 的对应测试类内（沿用该文件既有的页面构造方式；若该文件用 `QT_QPA_PLATFORM=offscreen` 下的 `QApplication`，照抄同类用例的写法）：

```python
    def test_transcript_shows_reply_target_and_intervention_reason(self):
        from brainstorm.models import DiscussionSession, Utterance, ViewpointKind
        from brainstorm.qt_app import RoundtablePage

        session = DiscussionSession(topic="社区养老", selected_role_ids=["builder", "skeptic"])
        session.append_utterance(Utterance("builder", "创业实践者", "先做小试点", ViewpointKind.OPPORTUNITY, "独立观点", origin="model"))
        session.append_utterance(Utterance("skeptic", "怀疑者", "没和替代方案比", ViewpointKind.RISK, "动态交锋",
                                          replies_to="event-000000", origin="model", intent="challenge"))
        page = RoundtablePage()
        page.session = session
        page._history = []
        page._utterance(session.utterances[1], 1, 2)
        self.assertIn("回应 创业实践者", page.transcript.toPlainText())

        session.discussion_state.host_intervention_reason = "发言集中在少数角色，讨论冷场"
        moderator = session.append_utterance(Utterance(
            "moderator", "主持人", "本阶段整理", ViewpointKind.SUMMARY, "状态整理", origin="model", intent="synthesize",
        ))
        page._utterance(moderator, 2, 3)
        self.assertIn("介入原因：发言集中在少数角色，讨论冷场", page.transcript.toPlainText())
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
& $py -m unittest tests.test_qt_ui -v
```

预期：新增用例 FAIL（`AssertionError`：转录里没有"回应 创业实践者"）。

- [ ] **Step 3: 实现两个标签辅助方法**

`brainstorm/qt_app.py`，在 `_utterance` 方法（第 599 行）之前插入：

```python
    def _reply_label(self, utterance: Utterance) -> str:
        if not utterance.replies_to or self.session is None:
            return ""
        target = next((item for item in self.session.utterances if item.event_id == utterance.replies_to), None)
        return f" · 回应 {target.speaker_name}" if target is not None else ""

    def _intervention_label(self, utterance: Utterance) -> str:
        if utterance.speaker_id != "moderator" or utterance.phase != "状态整理" or self.session is None:
            return ""
        reason = self.session.discussion_state.host_intervention_reason
        return f" · 介入原因：{reason}" if reason else ""
```

- [ ] **Step 4: 把它们接进气泡与转录**

`brainstorm/qt_app.py`，把 `_utterance` 里第 610 行的转录拼接：

```python
        self.transcript.append(f"【{utterance.phase}】 {utterance.speaker_name} · {utterance.kind.value}{intent}{stance} · {source}\n{utterance.content}\n")
```

替换为：

```python
        reply = self._reply_label(utterance)
        intervention = self._intervention_label(utterance)
        self.transcript.append(f"【{utterance.phase}】 {utterance.speaker_name} · {utterance.kind.value}{intent}{stance}{reply}{intervention} · {source}\n{utterance.content}\n")
```

再在 `_show_current_text`（第 612-619 行）里，把第 618 行的气泡赋值：

```python
        self.bubble.setText(f"{utterance.speaker_name}  ·  {utterance.kind.value}  ·  {source}\n{content}")
```

替换为：

```python
        self.bubble.setText(f"{utterance.speaker_name}  ·  {utterance.kind.value}{self._reply_label(utterance)}{self._intervention_label(utterance)}  ·  {source}\n{content}")
```

- [ ] **Step 5: 运行测试确认通过**

```powershell
& $py -m unittest tests.test_qt_ui -v
```

预期：全 PASS。

- [ ] **Step 6: 提交**

```powershell
git add brainstorm/qt_app.py tests/test_qt_ui.py
git commit -m "feat: show reply target and moderator intervention reason"
```

---

## Task 9: 全套回归与手工验收

**Files:**
- 无代码改动

- [ ] **Step 1: 运行全套测试**

```powershell
& $py -m unittest discover -s tests
```

预期：`Ran 127 tests` 或更多（新增测试会推高总数），且 `OK`，**0 errors 0 failures**。

若卡住不动，改用：

```powershell
& $py tools/run_tests_sandboxed.py
```

- [ ] **Step 2: 确认没有回归手动逐条展示**

```powershell
& $py -m unittest tests.test_generation_controller.GenerationControllerTests.test_default_discussion_waits_for_click_without_timer tests.test_qt_ui.QtUiTests.test_generation_progress_never_displays_raw_model_payload tests.test_qt_ui.QtUiTests.test_manual_generation_keeps_current_argument_visible -v
```

预期：三条都 PASS。这三条是上一轮修复的回归保护，**必须保持通过**。

若 `test_generation_progress_never_displays_raw_model_payload` 报类名不对，先用 `& $py -m unittest discover -s tests -v 2>&1 | Select-String "never_displays_raw_model_payload"` 找到它实际所在的类，再按实际名字重跑。

- [ ] **Step 3: 真实模型手工验收（**必须由用户执行**）**

用桌面版或 `python app.py` 打开程序，配置好 DeepSeek，跑一场真实讨论，逐条点击观察：

1. 反思记录里是否开始出现"支持 / 反驳 / 追问 / 补充"，而不是清一色"假设"。
2. 被反驳的角色，下一条是否出来回应那条反驳。
3. 是否存在"回应 XXX"标记。
4. 一次点击是否只多出一条发言（没有自动播放）。

**这一步的结论只能由用户给出。实施者不得以自己的观察代替，也不得宣称"讨论变深刻了"**——设计文档 §8 明确写了此项不得由实施者代为宣称通过。

- [ ] **Step 4: 提交**

```powershell
git add -A
git commit -m "test: verify conversation model phases 1-2"
```

---

## 收尾：更新记忆文件

第一期与第二期落地后，在 `PROJECT_MEMORY.md` 补一小节，记录：

- `brainstorm/turn_planner.py` 的职责与它**不做**语义判断这一边界；
- `extend_batch` 已不再按名册轮转；
- 第四期仍未完成（编排层、质检层、长讨论上下文、格式重试）；
- 真实模型长讨论的实际手感仍待用户验收。

---

## Self-Review 记录

**Spec 覆盖检查**（对照 `2026-10-12-conversation-model-design.md`）：

| Spec 章节 | 覆盖任务 |
| --- | --- |
| §5.1 提示词索要 intent／stance_change／event_id | Task 1 |
| §5.1 按人名回指取最新 | Task 2 |
| §5.1 代码围栏剥离 | Task 3 |
| §5.1 立场变化第四项并入 reason | Task 1 Step 5（提示词第 4 条） |
| §5.2 五条优先级规则 | Task 4 |
| §5.2 兜底不做语义判断 | Task 4（模块 docstring 与 `_least_spoken` 说明） |
| §5.2 从不连续三次同一角色 | Task 4 `_guard` |
| §8 五个介入触发条件可测 | Task 5 |
| §7 编排失败回退本地兜底 | Task 6（`plan_turn` 即兜底；编排层在第三期接入） |
| §6 界面显示回应对象与介入原因 | Task 8 |
| §8 回归保护一次点击一条 | Task 9 Step 2 |
| §6 主持人整理独立样式 | **未覆盖**，归入第三期（需先有编排层判定介入） |

**已知未覆盖项（有意延后到第三／四期计划）：** 调用 A 编排层、调用 C 质检层、后台预取与并发约束、三段式长讨论上下文（12 → 24 条与常驻段）、格式错误重试与回灌、重复检测置 `duplicate=True`（`detect_intervention` 已消费该标记，但模型路径尚无代码写入它）、主持人整理独立视觉样式、结束总结多遍。

**类型一致性检查：** `TurnPlan` 的字段在 Task 4 定义（`speaker_id`／`speaker_name`／`phase`／`intent`／`kind_hint`／`reply_to_event_id`／`reason`／`moderator`／`intervention_reason`／`source`），在 Task 6 的 `extend_batch` 中按同名使用；`detect_intervention(session, recent=6) -> tuple[bool, str]` 在 Task 4 定义，在 Task 7 按 `detect_intervention(self.session)[1]` 使用，签名一致；`plan_turn(session, roles, state=None)` 在 Task 4 定义并在 Task 6 以位置参数加 `state` 调用，一致。
