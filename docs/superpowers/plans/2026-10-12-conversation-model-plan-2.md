# 九人圆桌对话模型（第三期 + 第四期）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让每条发言都真的推进当前关键问题——每次生成前加一次模型"编排"调用（定关键问题、定谁说话、定这条必须回答什么，并顺带刷新状态），生成后加一次"质检"调用（查重复、查回避、查编造），不合格回炉一次。

**Architecture:** 新增 `brainstorm/orchestration.py` 承担编排与质检的提示词构造与结果解析；`brainstorm/jsonutil.py` 抽出共享的 JSON 剥围栏与校验，避免 `llm.py` 与 `orchestration.py` 循环依赖。`llm.py` 的 `extend_batch` 从"只调本地调度器"变为"本地调度器出结构事实 → 编排调用出语义决定 → 生成 → 质检 → 必要时回炉"。本地调度器**保留为兜底**，编排调用失败时无缝退回。

**Tech Stack:** Python 3、unittest（本项目**不用 pytest**）、标准库 `urllib.request`、PySide6/Qt。

**前置状态：** 第一、二期已完成（`conversation-model` 分支，9 个提交，152 项测试通过）。`turn_planner.py` 已存在并提供 `plan_turn` / `detect_intervention` / `TurnPlan`。

**本计划明确延后（不在本期范围）：**

- **后台预取**：它只影响等待时间，不影响讨论有效性，却要改动线程模型与并发约束，风险收益比不合适。
- **结束总结多遍成稿**：属于输出环节优化，不是讨论过程有效性。

这两项与本期不冲突，将来可单独出计划。

---

## 全局约定

**Python 解释器：**

```
C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
```

**每个新 shell 先设置环境：**

```powershell
$ws = (Resolve-Path '.').Path
$env:PYTHONPATH = $ws + ';' + (Resolve-Path '.qt-build-runtime').Path
$env:QT_QPA_PLATFORM = 'offscreen'
$py = 'C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
```

**运行单个模块：** `& $py -m unittest tests.test_orchestration -v`
**运行全套：** `& $py -m unittest discover -s tests`
**当前基线：** Ran 152 tests / OK。若卡住不动，改用 `& $py tools/run_tests_sandboxed.py`。

**不要做的事：** 不改 `brainstorm/engine.py`；不改存储格式（schema 仍为 v6）；不给 `Utterance`／`DiscussionState` 加字段；不引入固定轮数上限；不做自动播放。

**线程约定：** `extend_batch` 在后台线程运行，**不得直接改 `session`**。模型返回的状态刷新通过 provider 上的 `last_state_refresh` 属性交给主线程，由 `_apply_batch` 应用（与既有的 `last_usage` 同一套路）。

---

## Task 1: 抽出共享的 JSON 工具

`_strip_code_fence` 现在在 `llm.py` 里，编排与质检也要用。先抽出来，避免后面 `llm.py` 与 `orchestration.py` 互相 import。

**Files:**
- Create: `brainstorm/jsonutil.py`
- Create: `tests/test_jsonutil.py`
- Modify: `brainstorm/llm.py`（删掉本地 `_strip_code_fence`，改为 import）

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_jsonutil.py`：

```python
import unittest

from brainstorm.jsonutil import load_json_object, strip_code_fence


class JsonUtilTests(unittest.TestCase):
    def test_strip_code_fence_removes_language_tag_and_trailing_fence(self):
        self.assertEqual(strip_code_fence('```json\n{"a":1}\n```'), '{"a":1}')

    def test_strip_code_fence_leaves_plain_text_alone(self):
        self.assertEqual(strip_code_fence('  {"a":1}  '), '{"a":1}')

    def test_load_json_object_parses_fenced_object(self):
        self.assertEqual(load_json_object('```json\n{"a": 1}\n```'), {"a": 1})

    def test_load_json_object_rejects_non_object(self):
        with self.assertRaises(ValueError):
            load_json_object('[1, 2]')

    def test_load_json_object_rejects_malformed_json(self):
        with self.assertRaises(ValueError):
            load_json_object('{"a": ')
```

- [ ] **Step 2: 运行确认失败**

```powershell
& $py -m unittest tests.test_jsonutil -v
```

预期：`ModuleNotFoundError: No module named 'brainstorm.jsonutil'`。

- [ ] **Step 3: 实现**

创建 `brainstorm/jsonutil.py`：

```python
"""Shared helpers for the JSON objects the model is asked to return."""

from __future__ import annotations

import json


def strip_code_fence(text: str) -> str:
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


def load_json_object(text: str) -> dict:
    """Parse one JSON object, tolerating a code fence. Raises ValueError."""
    try:
        data = json.loads(strip_code_fence(text))
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("返回内容不是合法 JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("返回内容不是 JSON 对象")
    return data
```

- [ ] **Step 4: 运行确认通过**

```powershell
& $py -m unittest tests.test_jsonutil -v
```

预期：5 项全 PASS。

- [ ] **Step 5: 让 `llm.py` 复用它（去重，删掉本地副本）**

`brainstorm/llm.py`：删除模块级的 `def _strip_code_fence(...)` 整个函数，在 import 区加入：

```python
from .jsonutil import strip_code_fence
```

并把 `_parse` 里的 `json.loads(_strip_code_fence(text))` 与 OpenAI `_request` 里的 `text = _strip_code_fence(text)` 都改为 `strip_code_fence(...)`。

- [ ] **Step 6: 全套确认没坏**

```powershell
& $py -m unittest discover -s tests
```

预期：Ran 157 tests / OK（152 + 新增 5）。

- [ ] **Step 7: 提交**

```powershell
git add brainstorm/jsonutil.py brainstorm/llm.py tests/test_jsonutil.py
git commit -m "refactor: share the code-fence and JSON-object helpers"
```

---

## Task 2: JSON 格式错误回灌重试，不再整批掉回离线

用户反馈过的"怎么突然变离线了"，主要来源就是模型格式手滑一次就丢掉整条发言。协议 §6 要求"自动重试一次"。

**Files:**
- Modify: `brainstorm/llm.py`（`generate_turn`）
- Test: `tests/test_b_integration.py`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_b_integration.py` 的 `BIntegrationTests` 类内：

```python
    def test_malformed_json_is_retried_once_with_the_error(self):
        prompts = []

        class Event:
            def __init__(self, text): self.text = text

        class Stream:
            def __init__(self, text): self._text = text
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event(self._text)])

        class Messages:
            def __init__(self): self.calls = 0
            def stream(self, **kwargs):
                self.calls += 1
                prompts.append(kwargs["messages"][0]["content"])
                # 第一次返回坏 JSON，第二次返回合法内容
                return Stream('{"content": ' if self.calls == 1 else '{"content":"修正后的观点","kind":"机会"}')

        class Client:
            def __init__(self): self.messages = Messages()

        client = Client()
        provider = AnthropicDiscussionProvider(client=client, model="test-model")
        result = provider.generate_turn("主题", [], [], [], TurnSpec("moderator", "主持人", "开场"))
        self.assertEqual(result.utterance.content, "修正后的观点")
        self.assertEqual(client.messages.calls, 2)
        # 第二次请求必须把错误回灌给模型
        self.assertIn("不是合法 JSON", prompts[1])

    def test_malformed_json_twice_still_falls_back_honestly(self):
        class Event:
            text = '{"content": '

        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])

        class Messages:
            def stream(self, **_): return Stream()

        class Client:
            messages = Messages()

        provider = AnthropicDiscussionProvider(client=Client(), model="test-model")
        with self.assertRaises(ProviderFailure) as ctx:
            provider.generate_turn("主题", [], [], [], TurnSpec("moderator", "主持人", "开场"))
        self.assertEqual(ctx.exception.code, "malformed_json")
```

- [ ] **Step 2: 运行确认失败**

```powershell
& $py -m unittest tests.test_b_integration.BIntegrationTests.test_malformed_json_is_retried_once_with_the_error -v
```

预期：FAIL，抛 `ProviderFailure`（第一次坏 JSON 就直接失败，没有第二次请求）。

- [ ] **Step 3: 实现**

`brainstorm/llm.py`，把 `generate_turn` 里这一段：

```python
        response = self._request(prompt, on_partial=on_partial, cancel_event=cancel_event)
        parsed = self._parse(response.text, spec, history)
        usage = response.usage
        self.last_usage = self.last_usage.add(usage)
        return TurnResult(parsed[0], parsed[1], usage)
```

替换为：

```python
        response = self._request(prompt, on_partial=on_partial, cancel_event=cancel_event)
        usage = response.usage
        try:
            parsed = self._parse(response.text, spec, history)
        except ProviderFailure as exc:
            if exc.code != "malformed_json":
                raise
            # Feed the parse error back once instead of discarding the turn and
            # dropping the whole discussion back to offline simulation.
            repair_prompt = (
                prompt
                + f"\n\n你上一次的返回不是合法 JSON，错误是：{exc.safe_message}。"
                "请只输出一个合法的 JSON 对象，不要 markdown，不要代码围栏，不要任何解释。\n"
            )
            repaired = self._request(repair_prompt, on_partial=on_partial, cancel_event=cancel_event)
            usage = usage.add(repaired.usage)
            parsed = self._parse(repaired.text, spec, history)
        self.last_usage = self.last_usage.add(usage)
        return TurnResult(parsed[0], parsed[1], usage)
```

再把 `_parse` 里的 JSON 解析失败改为抛出带可读信息的错误（它已经是 `ProviderFailure("malformed_json", ...)`，无需改动）。

- [ ] **Step 4: 运行确认通过**

```powershell
& $py -m unittest tests.test_b_integration -v
```

预期：全 PASS，含两条新测试。

- [ ] **Step 5: 提交**

```powershell
git add brainstorm/llm.py tests/test_b_integration.py
git commit -m "feat: retry a malformed model response once instead of dropping the turn"
```

---

## Task 3: 重复检测写入 `duplicate` 标记

`detect_intervention` 已经在消费 `duplicate`，但模型路径没有任何代码写它，所以"重复观点增加"这个触发条件在真实使用中是空的。

**Files:**
- Modify: `brainstorm/turn_planner.py`（新增 `mark_duplicates`）
- Test: `tests/test_turn_planner.py`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_turn_planner.py` 的 `TurnPlannerTests` 类内：

```python
    def test_repeated_content_is_marked_without_being_deleted(self):
        session = build(
            say("trend", "趋势分析师", "先做小范围试点"),
            say("builder", "创业实践者", "先 做 小范围 试点"),
            say("skeptic", "怀疑者", "完全不同的观点"),
        )
        marked = mark_duplicates(session)
        self.assertEqual(marked, 1)
        self.assertEqual(len(session.utterances), 3)
        self.assertFalse(session.utterances[0].duplicate)
        self.assertTrue(session.utterances[1].duplicate)
        self.assertFalse(session.utterances[2].duplicate)

    def test_duplicate_marking_ignores_moderator_and_user_turns(self):
        session = build(
            say("moderator", "主持人", "本阶段整理"),
            say("moderator", "主持人", "本阶段整理"),
        )
        self.assertEqual(mark_duplicates(session), 0)
```

并在文件顶部 import 里加上 `mark_duplicates`：

```python
from brainstorm.turn_planner import TurnPlan, detect_intervention, mark_duplicates, plan_turn
```

- [ ] **Step 2: 运行确认失败**

```powershell
& $py -m unittest tests.test_turn_planner -v
```

预期：`ImportError: cannot import name 'mark_duplicates'`。

- [ ] **Step 3: 实现**

`brainstorm/turn_planner.py`，在 `detect_intervention` 之前插入：

```python
def mark_duplicates(session: DiscussionSession) -> int:
    """Flag repeats of an earlier role turn. Never deletes anything.

    The protocol requires repeated content to stay in the record with only a
    marker added.  Comparison is deliberately blunt -- whitespace-stripped exact
    match -- so the marker is explainable rather than a similarity guess.
    """
    seen: set[str] = set()
    marked = 0
    for index, item in enumerate(session.utterances):
        if item.speaker_id in {MODERATOR_ID, USER_ID}:
            continue
        normalized = re.sub(r"\s+", "", item.content)
        if normalized in seen:
            if not item.duplicate:
                session.utterances[index] = replace(item, duplicate=True)
            marked += 1
        else:
            seen.add(normalized)
    return marked
```

并在文件顶部加入 `import re`。

- [ ] **Step 4: 运行确认通过**

```powershell
& $py -m unittest tests.test_turn_planner -v
```

预期：18 项全 PASS。

- [ ] **Step 5: 让控制器在落盘时调用它**

`brainstorm/session_controller.py`，把 import 改为：

```python
from .turn_planner import detect_intervention, mark_duplicates
```

并在 `_apply_batch` 里 `self.session.rebuild_state()` 之后、计算介入原因之前插入：

```python
        mark_duplicates(self.session)
```

- [ ] **Step 6: 写一条控制器级测试**

追加到 `tests/test_generation_controller.py` 的 `GenerationControllerTests` 类内：

```python
    def test_batch_marks_repeated_role_content(self):
        controller = self.track(SessionController(store=SessionStore(self._history_tmp)))
        session = DiscussionSession(topic="社区养老", selected_role_ids=["trend"])
        session.append_utterance(Utterance("trend", "趋势分析师", "先做小范围试点", ViewpointKind.ASSUMPTION, "动态交锋", origin="model"))
        controller.playback.live = True
        controller.playback.start(session)
        controller._apply_batch([Utterance("trend", "趋势分析师", "先 做 小范围 试点", ViewpointKind.ASSUMPTION, "动态交锋", origin="model")])
        self.assertTrue(session.utterances[-1].duplicate)
        self.assertEqual(len(session.utterances), 2)
```

- [ ] **Step 7: 运行确认通过**

```powershell
& $py -m unittest tests.test_generation_controller tests.test_turn_planner -v
```

预期：全 PASS。

- [ ] **Step 8: 提交**

```powershell
git add brainstorm/turn_planner.py brainstorm/session_controller.py tests/test_turn_planner.py tests/test_generation_controller.py
git commit -m "feat: mark repeated role turns so the repetition trigger can fire"
```

---

## Task 4: 编排调用的提示词与解析

**Files:**
- Create: `brainstorm/orchestration.py`
- Create: `tests/test_orchestration.py`

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_orchestration.py`：

```python
import unittest

from brainstorm.models import DiscussionSession, DiscussionState, Role, Utterance, ViewpointKind
from brainstorm.orchestration import (
    OrchestrationRefresh,
    build_orchestration_prompt,
    build_review_prompt,
    parse_orchestration,
    parse_review,
)
from brainstorm.turn_planner import TurnPlan


ROLES = [
    Role("trend", "趋势分析师", "辨别变化", "#2563eb", "关注变化是否真实。"),
    Role("builder", "创业实践者", "把机会转成产品", "#7c3aed", "关注谁付费。"),
]


def session_with(*utterances):
    session = DiscussionSession(topic="社区养老", selected_role_ids=["trend", "builder"])
    for item in utterances:
        session.append_utterance(item)
    return session


class OrchestrationPromptTests(unittest.TestCase):
    def test_prompt_includes_roster_event_ids_and_local_facts(self):
        session = session_with(Utterance("trend", "趋势分析师", "现有观点", ViewpointKind.OPPORTUNITY, "独立观点", origin="model"))
        local = TurnPlan("builder", "创业实践者", "正面反驳", "challenge", reason="趋势分析师的质疑尚未回应")
        prompt = build_orchestration_prompt(session, ROLES, local)
        self.assertIn("社区养老", prompt)
        self.assertIn("trend", prompt)
        self.assertIn("builder", prompt)
        self.assertIn("event-000000", prompt)
        self.assertIn("质疑尚未回应", prompt)
        self.assertIn("consensus", prompt)
        self.assertIn("moderator", prompt)

    def test_prompt_states_sources_are_unverified(self):
        session = session_with()
        prompt = build_orchestration_prompt(session, ROLES, TurnPlan("trend", "趋势分析师", "回应", "elaborate"))
        self.assertIn("未核验", prompt)


class OrchestrationParseTests(unittest.TestCase):
    def test_parses_plan_and_state_refresh(self):
        session = session_with(Utterance("trend", "趋势分析师", "现有观点", ViewpointKind.OPPORTUNITY, "独立观点", origin="model"))
        payload = (
            '{"key_question":"第一批用户为什么不用现成的？","speaker_id":"builder",'
            '"must_answer":"给出与现有替代方案的对比","avoid":["重复讲趋势"],'
            '"intervene":false,"intervention_reason":"",'
            '"consensus":["先做小范围试点"],"conflicts":["需求强度未验证"],"unresolved":["付费意愿"]}'
        )
        plan, refresh = parse_orchestration(payload, session, ROLES, TurnPlan("trend", "趋势分析师", "回应", "elaborate"))
        self.assertEqual(plan.speaker_id, "builder")
        self.assertEqual(plan.speaker_name, "创业实践者")
        self.assertEqual(plan.source, "model")
        self.assertEqual(plan.must_answer, "给出与现有替代方案的对比")
        self.assertEqual(plan.avoid, ("重复讲趋势",))
        self.assertEqual(plan.key_question, "第一批用户为什么不用现成的？")
        self.assertEqual(refresh.consensus, ("先做小范围试点",))
        self.assertEqual(refresh.conflicts, ("需求强度未验证",))
        self.assertEqual(refresh.unresolved, ("付费意愿",))

    def test_moderator_decision_produces_an_intervention_plan(self):
        session = session_with()
        payload = (
            '{"key_question":"是否已有共识？","speaker_id":"moderator","must_answer":"整理共识",'
            '"avoid":[],"intervene":true,"intervention_reason":"已出现重要共识",'
            '"consensus":[],"conflicts":[],"unresolved":[]}'
        )
        plan, _ = parse_orchestration(payload, session, ROLES, TurnPlan("trend", "趋势分析师", "回应", "elaborate"))
        self.assertTrue(plan.moderator)
        self.assertEqual(plan.phase, "状态整理")
        self.assertEqual(plan.intervention_reason, "已出现重要共识")

    def test_unknown_speaker_raises_so_the_caller_can_fall_back(self):
        session = session_with()
        payload = '{"key_question":"x","speaker_id":"nobody","must_answer":"y","avoid":[],"intervene":false,"intervention_reason":"","consensus":[],"conflicts":[],"unresolved":[]}'
        with self.assertRaises(ValueError):
            parse_orchestration(payload, session, ROLES, TurnPlan("trend", "趋势分析师", "回应", "elaborate"))

    def test_malformed_payload_raises(self):
        session = session_with()
        with self.assertRaises(ValueError):
            parse_orchestration('{"key_question": ', session, ROLES, TurnPlan("trend", "趋势分析师", "回应", "elaborate"))


class ReviewTests(unittest.TestCase):
    def test_review_prompt_contains_target_and_content(self):
        session = session_with(Utterance("trend", "趋势分析师", "现有观点", ViewpointKind.OPPORTUNITY, "独立观点", origin="model"))
        plan = TurnPlan("builder", "创业实践者", "正面反驳", "challenge", must_answer="给出对比数据", reason="x")
        utterance = Utterance("builder", "创业实践者", "我给出对比", ViewpointKind.RISK, "正面反驳", origin="model")
        prompt = build_review_prompt(session, plan, utterance)
        self.assertIn("给出对比数据", prompt)
        self.assertIn("我给出对比", prompt)

    def test_passing_review(self):
        review = parse_review('{"passed":true,"repeats":"","avoided":"","fabricated":""}')
        self.assertTrue(review.passed)
        self.assertEqual(review.criticism, "")

    def test_failing_review_builds_a_concrete_criticism(self):
        review = parse_review(
            '{"passed":false,"repeats":"重复了 event-000000 的趋势判断",'
            '"avoided":"回避了被要求的对比数据","fabricated":"引用了来源里没有的数字"}'
        )
        self.assertFalse(review.passed)
        self.assertIn("重复了 event-000000 的趋势判断", review.criticism)
        self.assertIn("回避了被要求的对比数据", review.criticism)
        self.assertIn("引用了来源里没有的数字", review.criticism)

    def test_malformed_review_raises(self):
        with self.assertRaises(ValueError):
            parse_review("not json")
```

- [ ] **Step 2: 运行确认失败**

```powershell
& $py -m unittest tests.test_orchestration -v
```

预期：`ModuleNotFoundError: No module named 'brainstorm.orchestration'`。

- [ ] **Step 3: 实现**

创建 `brainstorm/orchestration.py`：

```python
"""Model-driven orchestration and quality control around each generated turn.

The local planner answers structural questions exactly but cannot judge what
the discussion is really about.  This module adds the two model calls that can:

* ``build_orchestration_prompt`` / ``parse_orchestration`` decide the single most
  important open question, who speaks next and what that turn must answer, and
  refresh the discussion state in the same call.
* ``build_review_prompt`` / ``parse_review`` judge whether the generated turn
  actually advanced the discussion.

Both halves are pure prompt-builders and parsers; the provider performs the
request.  Any parse failure raises ``ValueError`` so the caller can fall back to
the local plan instead of losing the turn.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from .jsonutil import load_json_object
from .models import DiscussionSession, DiscussionState, Role, Utterance
from .turn_planner import MODERATOR_ID, TurnPlan

HISTORY_LIMIT = 24
MAX_LIST_ITEMS = 4
MAX_AVOID_ITEMS = 3


@dataclass(frozen=True)
class OrchestrationRefresh:
    consensus: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()


@dataclass(frozen=True)
class Review:
    passed: bool
    repeats: str = ""
    avoided: str = ""
    fabricated: str = ""

    @property
    def criticism(self) -> str:
        parts = [part for part in (self.repeats, self.avoided, self.fabricated) if part]
        return "；".join(parts)


def render_event_stream(session: DiscussionSession, *, limit: int = HISTORY_LIMIT) -> str:
    rendered = []
    for item in session.utterances[-limit:]:
        target = f" →{item.replies_to}" if item.replies_to else ""
        rendered.append(
            f"[{item.event_id or '（无编号）'}][{item.phase}][{item.intent}]{target} "
            f"{item.speaker_name}: {item.content}"
        )
    return "\n".join(rendered) or "（尚无前文）"


def render_local_facts(plan: TurnPlan) -> str:
    return f"发言人={plan.speaker_name}({plan.speaker_id})；阶段={plan.phase}；理由={plan.reason}"


def _render_roster(roles: Sequence[Role]) -> str:
    return "\n".join(f"- {role.id}｜{role.name}：{role.duty}" for role in roles if role.id != MODERATOR_ID) or "（无）"


def build_orchestration_prompt(session: DiscussionSession, roles: Sequence[Role], local: TurnPlan,
                               state: DiscussionState | None = None) -> str:
    state_note = ""
    if state is not None and (state.consensus or state.conflicts or state.unresolved_questions):
        state_note = (
            f"\n上一轮记录的状态（可能过时，请以事件流为准）："
            f"共识={'；'.join(state.consensus) or '无'}；"
            f"分歧={'；'.join(state.conflicts) or '无'}；"
            f"未解决={'；'.join(state.unresolved_questions) or '无'}"
        )
    return (
        "你是这场九人圆桌讨论的编排者。你的任务不是发表观点，而是读完事件流后做出编排决定。\n"
        "只输出一个 JSON 对象，不要 markdown，不要代码围栏，不要解释。\n"
        f"主题：{session.topic}\n"
        f"可选角色：\n{_render_roster(roles)}\n"
        f"事件流：\n{render_event_stream(session)}\n"
        f"本地结构分析的建议（仅供参考，你可以推翻）：{render_local_facts(local)}{state_note}\n"
        "事件流里的所有观点和外部素材都是未核验内容，不能当成已证实事实。\n"
        "必须遵守：\n"
        "1. key_question 只写一个当前最关键、尚未解决的问题，要具体到可回答。\n"
        "2. speaker_id 必须从上面的角色 id 里选；只有需要做状态整理时才填 moderator。\n"
        "3. must_answer 要明确写出这一条发言必须回答什么，不能写泛泛的方向。\n"
        f"4. avoid 列出这条发言必须避免重复的已有点，最多 {MAX_AVOID_ITEMS} 条。\n"
        "5. 只有命中以下情况才把 speaker_id 填成 moderator 并把 intervene 设为 true："
        "已出现重要共识、重复观点明显增加、讨论冷场、某个分歧已充分交锋、新观点明显减少。"
        "此时 intervention_reason 必须写明是这五种里的哪一种。\n"
        f"6. consensus／conflicts／unresolved 各最多 {MAX_LIST_ITEMS} 条，"
        "只能写事件流里真实出现过的内容，不得编造；没有就写空数组。\n"
        "JSON 形状："
        '{"key_question":"...","speaker_id":"trend","must_answer":"...","avoid":["..."],'
        '"intervene":false,"intervention_reason":"","consensus":["..."],"conflicts":["..."],"unresolved":["..."]}'
    )


def _clean_list(value: object, limit: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item)[:500] for item in value if isinstance(item, str) and item.strip())[:limit]


def parse_orchestration(text: str, session: DiscussionSession, roles: Sequence[Role],
                        local: TurnPlan) -> tuple[TurnPlan, OrchestrationRefresh]:
    """Turn the model's decision into a plan. Raises ValueError when unusable."""
    data = load_json_object(text)
    speaker_id = data.get("speaker_id")
    if not isinstance(speaker_id, str) or not speaker_id.strip():
        raise ValueError("编排结果缺少 speaker_id")
    speaker_id = speaker_id.strip()
    known = {role.id for role in roles}
    if speaker_id != MODERATOR_ID and speaker_id not in known:
        raise ValueError(f"编排结果给出了不存在的角色：{speaker_id}")

    must_answer = data.get("must_answer")
    if not isinstance(must_answer, str) or not must_answer.strip():
        raise ValueError("编排结果缺少 must_answer")
    key_question = data.get("key_question")
    intervene = bool(data.get("intervene"))
    reason = data.get("intervention_reason")
    reason = reason.strip() if isinstance(reason, str) else ""

    if speaker_id == MODERATOR_ID:
        if not intervene:
            intervene = True
        if not reason:
            reason = "需要主持人整理当前讨论"
        plan = replace(
            local,
            speaker_id=MODERATOR_ID,
            speaker_name="主持人",
            phase="状态整理",
            intent="synthesize",
            kind_hint="总结",
            moderator=True,
            intervention_reason=reason,
            must_answer=must_answer.strip()[:500],
            key_question=key_question.strip()[:500] if isinstance(key_question, str) else "",
            reason=reason,
            source="model",
        )
    else:
        speaker = next(role for role in roles if role.id == speaker_id)
        plan = replace(
            local,
            speaker_id=speaker.id,
            speaker_name=speaker.name,
            moderator=False,
            intervention_reason="",
            must_answer=must_answer.strip()[:500],
            key_question=key_question.strip()[:500] if isinstance(key_question, str) else "",
            avoid=_clean_list(data.get("avoid"), MAX_AVOID_ITEMS),
            source="model",
        )

    refresh = OrchestrationRefresh(
        consensus=_clean_list(data.get("consensus"), MAX_LIST_ITEMS),
        conflicts=_clean_list(data.get("conflicts"), MAX_LIST_ITEMS),
        unresolved=_clean_list(data.get("unresolved"), MAX_LIST_ITEMS),
    )
    return plan, refresh


def build_review_prompt(session: DiscussionSession, plan: TurnPlan, utterance: Utterance) -> str:
    required = plan.must_answer or "推进当前尚未解决的关键问题"
    avoid = "；".join(plan.avoid) if plan.avoid else "无"
    return (
        "你是这场圆桌讨论的质检者。判断下面这一条刚生成的发言是否真的推进了讨论。\n"
        "只输出一个 JSON 对象，不要 markdown，不要代码围栏，不要解释。\n"
        f"主题：{session.topic}\n"
        f"本次被指派必须回答：{required}\n"
        f"本次必须避免重复：{avoid}\n"
        f"事件流：\n{render_event_stream(session)}\n"
        f"刚生成的发言（发言人：{utterance.speaker_name}）：\n{utterance.content}\n"
        "逐项检查并给出具体证据，不要写空泛评语：\n"
        "1. repeats：是否只是重复前文已有观点？是则指出重复的是哪个 event_id 或哪一句，否则留空。\n"
        "2. avoided：是否回避了本次被指派必须回答的内容？是则指出回避了什么，否则留空。\n"
        "3. fabricated：是否编造了来源材料中不存在的数据、引用或事实？是则指出编造了什么，否则留空。\n"
        "任意一项非空即视为不合格，passed 必须为 false。\n"
        'JSON 形状：{"passed":true,"repeats":"","avoided":"","fabricated":""}'
    )


def parse_review(text: str) -> Review:
    data = load_json_object(text)
    if "passed" not in data:
        raise ValueError("质检结果缺少 passed")
    def field(name: str) -> str:
        value = data.get(name)
        return value.strip()[:500] if isinstance(value, str) else ""
    repeats, avoided, fabricated = field("repeats"), field("avoided"), field("fabricated")
    passed = bool(data.get("passed")) and not (repeats or avoided or fabricated)
    return Review(passed=passed, repeats=repeats, avoided=avoided, fabricated=fabricated)
```

- [ ] **Step 4: `TurnPlan` 需要新增三个字段**

`brainstorm/turn_planner.py`，把 `TurnPlan` 改为：

```python
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
    must_answer: str = ""
    avoid: tuple[str, ...] = ()
    key_question: str = ""
```

- [ ] **Step 5: 运行确认通过**

```powershell
& $py -m unittest tests.test_orchestration tests.test_turn_planner -v
```

预期：全 PASS（编排 12 项 + 调度 18 项）。

- [ ] **Step 6: 提交**

```powershell
git add brainstorm/orchestration.py brainstorm/turn_planner.py tests/test_orchestration.py
git commit -m "feat: add orchestration and review prompts with defensive parsing"
```

---

## Task 5: 把编排接入 `extend_batch`，本地计划降为兜底

**Files:**
- Modify: `brainstorm/llm.py`（`extend_batch`、`generate_turn` 的指令段）
- Test: `tests/test_b_integration.py`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_b_integration.py` 的 `BIntegrationTests` 类内：

```python
    def test_extend_batch_honours_the_orchestrator_decision(self):
        prompts = []

        class Event:
            def __init__(self, text): self.text = text

        class Stream:
            def __init__(self, text): self._text = text
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event(self._text)])

        ORCHESTRATION = (
            '{"key_question":"谁先付费？","speaker_id":"skeptic",'
            '"must_answer":"说明第一批用户为什么今天就要解决","avoid":["重复讲趋势"],'
            '"intervene":false,"intervention_reason":"",'
            '"consensus":["先做小范围试点"],"conflicts":["需求强度未验证"],"unresolved":["付费意愿"]}'
        )

        class Messages:
            def __init__(self): self.calls = 0
            def stream(self, **kwargs):
                self.calls += 1
                prompts.append(kwargs["messages"][0]["content"])
                if self.calls == 1:
                    return Stream(ORCHESTRATION)
                return Stream('{"content":"我来说明付费动机","kind":"风险","intent":"challenge"}')

        class Client:
            def __init__(self): self.messages = Messages()

        client = Client()
        provider = AnthropicDiscussionProvider(client=client, model="test-model")
        session = DiscussionSession(topic="社区养老", selected_role_ids=["builder", "skeptic"])
        session.append_utterance(Utterance("builder", "创业实践者", "先做小试点", ViewpointKind.OPPORTUNITY, "独立观点", origin="model"))
        roles = [
            Role("builder", "创业实践者", "把机会转成产品", "#7c3aed", "关注谁付费。"),
            Role("skeptic", "怀疑者", "寻找伪需求", "#dc2626", "主动寻找反例。"),
        ]
        added = provider.extend_batch(session, DiscussionState(), roles=roles)
        self.assertEqual(added[0].speaker_id, "skeptic")
        # 状态刷新随编排调用一起返回，交给主线程应用
        self.assertIsNotNone(provider.last_state_refresh)
        self.assertEqual(provider.last_state_refresh.consensus, ("先做小范围试点",))
        # 生成提示词必须带上"必须回答"和"必须避免"
        self.assertIn("第一批用户为什么今天就要解决", prompts[1])
        self.assertIn("重复讲趋势", prompts[1])

    def test_orchestration_failure_falls_back_to_the_local_plan(self):
        class Event:
            text = '{"content":"我回应质疑","intent":"challenge"}'

        class Stream:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event()])

        class Messages:
            def stream(self, **_): return Stream()

        class Client:
            messages = Messages()

        provider = AnthropicDiscussionProvider(client=Client(), model="test-model")
        session = DiscussionSession(topic="社区养老", selected_role_ids=["builder", "skeptic"])
        session.append_utterance(Utterance("builder", "创业实践者", "先做小试点", ViewpointKind.OPPORTUNITY, "独立观点", origin="model"))
        session.append_utterance(Utterance("skeptic", "怀疑者", "没和替代方案比", ViewpointKind.RISK, "动态交锋",
                                          replies_to="event-000000", origin="model", intent="challenge"))
        roles = [
            Role("builder", "创业实践者", "把机会转成产品", "#7c3aed", "关注谁付费。"),
            Role("skeptic", "怀疑者", "寻找伪需求", "#dc2626", "主动寻找反例。"),
        ]
        added = provider.extend_batch(session, DiscussionState(), roles=roles)
        # 编排结果无法解析（假客户端对每次请求都返回同一条发言），必须退回本地计划
        self.assertEqual(added[0].speaker_id, "builder")
        self.assertIsNone(provider.last_state_refresh)
```

- [ ] **Step 2: 运行确认失败**

```powershell
& $py -m unittest tests.test_b_integration.BIntegrationTests.test_extend_batch_honours_the_orchestrator_decision -v
```

预期：FAIL（`AttributeError: 'AnthropicDiscussionProvider' object has no attribute 'last_state_refresh'`，或断言 speaker 不符）。

- [ ] **Step 3: 实现**

`brainstorm/llm.py`，import 区加入：

```python
from .orchestration import (
    OrchestrationRefresh,
    build_orchestration_prompt,
    build_review_prompt,
    parse_orchestration,
    parse_review,
)
```

`__init__` 里，在 `self.last_usage = Usage()` 之后加入：

```python
        self.last_state_refresh: OrchestrationRefresh | None = None
```

把 `extend_batch` 的方法体替换为：

```python
        selected = list(roles)
        local = plan_turn(session, selected, state)
        self.last_state_refresh = None
        plan = local
        try:
            plan, refresh = self.orchestrate(session, selected, local, state, cancel_event=cancel_event)
            self.last_state_refresh = refresh
        except (ProviderFailure, ValueError):
            # Honest fallback: keep the structural plan rather than dropping the
            # turn. The controller notes that orchestration was unavailable.
            plan = local
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

在 `generate_turn` 之前新增编排方法：

```python
    def orchestrate(
        self,
        session: DiscussionSession,
        roles: Sequence[Role],
        local: TurnPlan,
        state: DiscussionState | None,
        *,
        cancel_event: threading.Event | None = None,
    ) -> tuple[TurnPlan, OrchestrationRefresh]:
        prompt = build_orchestration_prompt(session, roles, local, state)
        response = self._request(prompt, on_partial=None, cancel_event=cancel_event)
        self.last_usage = self.last_usage.add(response.usage)
        return parse_orchestration(response.text, session, roles, local)
```

把 `generate_turn` 里的指令段（`if plan is not None and plan.moderator:` 那一段）替换为：

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
            required = plan.must_answer or plan.reason
            avoid = f"必须避免重复：{'；'.join(plan.avoid)}。\n" if plan.avoid else ""
            prompt += (
                f"\n编排要求：本次发言必须回应 {target}，并且必须回答：{required}。"
                f"{avoid}"
                "若你认为回应对象不合适，可以改选，但必须在 intent 中如实表达。\n"
            )
```

- [ ] **Step 4: 运行确认通过**

```powershell
& $py -m unittest tests.test_b_integration -v
```

预期：全 PASS。

- [ ] **Step 5: 控制器应用状态刷新**

`brainstorm/session_controller.py`，在 `_apply_batch` 里 `mark_duplicates(self.session)` 之后插入：

```python
        refresh = getattr(self.provider, "last_state_refresh", None)
        if refresh is not None:
            self.session.discussion_state.consensus = list(refresh.consensus)
            self.session.discussion_state.conflicts = list(refresh.conflicts)
            self.session.discussion_state.unresolved_questions = list(refresh.unresolved)
            self.provider.last_state_refresh = None
```

- [ ] **Step 6: 写一条控制器测试**

追加到 `tests/test_generation_controller.py` 的 `GenerationControllerTests` 类内：

```python
    def test_batch_applies_the_model_state_refresh(self):
        from brainstorm.orchestration import OrchestrationRefresh

        controller = self.track(SessionController(store=SessionStore(self._history_tmp)))
        session = DiscussionSession(topic="社区养老", selected_role_ids=["trend"])
        session.append_utterance(Utterance("trend", "趋势分析师", "开场", ViewpointKind.ASSUMPTION, "独立观点", origin="model"))
        controller.playback.live = True
        controller.playback.start(session)
        controller.provider.last_state_refresh = OrchestrationRefresh(
            consensus=("先做小范围试点",), conflicts=("需求强度未验证",), unresolved=("付费意愿",),
        )
        controller._apply_batch([Utterance("trend", "趋势分析师", "继续", ViewpointKind.ASSUMPTION, "动态交锋", origin="model")])
        self.assertEqual(session.discussion_state.consensus, ["先做小范围试点"])
        self.assertEqual(session.discussion_state.conflicts, ["需求强度未验证"])
        self.assertIsNone(controller.provider.last_state_refresh)
```

- [ ] **Step 7: 运行确认通过**

```powershell
& $py -m unittest tests.test_generation_controller -v
```

预期：全 PASS。

- [ ] **Step 8: 提交**

```powershell
git add brainstorm/llm.py brainstorm/session_controller.py tests/test_b_integration.py tests/test_generation_controller.py
git commit -m "feat: let the orchestrator decide the turn and refresh state, local plan as fallback"
```

---

## Task 6: 质检与回炉重写

**Files:**
- Modify: `brainstorm/llm.py`（`extend_batch` 末尾、新增 `review_turn`）
- Test: `tests/test_b_integration.py`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_b_integration.py` 的 `BIntegrationTests` 类内：

```python
    def test_failing_review_triggers_exactly_one_rewrite(self):
        prompts = []

        class Event:
            def __init__(self, text): self.text = text

        class Stream:
            def __init__(self, text): self._text = text
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event(self._text)])

        ORCHESTRATION = (
            '{"key_question":"谁先付费？","speaker_id":"builder","must_answer":"说明付费动机","avoid":[],'
            '"intervene":false,"intervention_reason":"","consensus":[],"conflicts":[],"unresolved":[]}'
        )
        REJECT = '{"passed":false,"repeats":"重复了 event-000000","avoided":"回避了付费动机","fabricated":""}'
        ACCEPT = '{"passed":true,"repeats":"","avoided":"","fabricated":""}'

        class Messages:
            def __init__(self): self.calls = 0
            def stream(self, **kwargs):
                self.calls += 1
                prompts.append(kwargs["messages"][0]["content"])
                if self.calls == 1:
                    return Stream(ORCHESTRATION)
                if self.calls == 2:
                    return Stream('{"content":"第一版发言","kind":"机会","intent":"support"}')
                if self.calls == 3:
                    return Stream(REJECT)
                return Stream('{"content":"第二版发言","kind":"机会","intent":"support"}')

        class Client:
            def __init__(self): self.messages = Messages()

        client = Client()
        provider = AnthropicDiscussionProvider(client=client, model="test-model")
        session = DiscussionSession(topic="社区养老", selected_role_ids=["builder"])
        session.append_utterance(Utterance("builder", "创业实践者", "先做小试点", ViewpointKind.OPPORTUNITY, "独立观点", origin="model"))
        roles = [Role("builder", "创业实践者", "把机会转成产品", "#7c3aed", "关注谁付费。")]
        added = provider.extend_batch(session, DiscussionState(), roles=roles)
        self.assertEqual(added[0].content, "第二版发言")
        self.assertEqual(client.messages.calls, 4)
        # 回炉请求必须把具体批评带回去
        self.assertIn("重复了 event-000000", prompts[3])
        self.assertIn("回避了付费动机", prompts[3])

    def test_review_failure_keeps_the_turn_and_does_not_retry(self):
        class Event:
            def __init__(self, text): self.text = text

        class Stream:
            def __init__(self, text): self._text = text
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return iter([Event(self._text)])

        ORCHESTRATION = (
            '{"key_question":"q","speaker_id":"builder","must_answer":"m","avoid":[],'
            '"intervene":false,"intervention_reason":"","consensus":[],"conflicts":[],"unresolved":[]}'
        )

        class Messages:
            def __init__(self): self.calls = 0
            def stream(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return Stream(ORCHESTRATION)
                if self.calls == 2:
                    return Stream('{"content":"唯一一版","kind":"机会","intent":"support"}')
                return Stream('这不是 JSON')

        class Client:
            def __init__(self): self.messages = Messages()

        client = Client()
        provider = AnthropicDiscussionProvider(client=client, model="test-model")
        session = DiscussionSession(topic="社区养老", selected_role_ids=["builder"])
        session.append_utterance(Utterance("builder", "创业实践者", "先做小试点", ViewpointKind.OPPORTUNITY, "独立观点", origin="model"))
        roles = [Role("builder", "创业实践者", "把机会转成产品", "#7c3aed", "关注谁付费。")]
        added = provider.extend_batch(session, DiscussionState(), roles=roles)
        self.assertEqual(added[0].content, "唯一一版")
        self.assertEqual(client.messages.calls, 3)
        self.assertIsNone(provider.last_review)
```

- [ ] **Step 2: 运行确认失败**

```powershell
& $py -m unittest tests.test_b_integration.BIntegrationTests.test_failing_review_triggers_exactly_one_rewrite -v
```

预期：FAIL（`calls` 为 2 而不是 4，或 `last_review` 不存在）。

- [ ] **Step 3: 实现**

`brainstorm/llm.py`，`__init__` 里在 `self.last_state_refresh` 之后加入：

```python
        self.last_review: Review | None = None
```

import 区补上 `Review`：

```python
from .orchestration import (
    OrchestrationRefresh,
    Review,
    build_orchestration_prompt,
    build_review_prompt,
    parse_orchestration,
    parse_review,
)
```

在 `orchestrate` 之后新增：

```python
    def review_turn(
        self,
        session: DiscussionSession,
        plan: TurnPlan,
        utterance: Utterance,
        *,
        cancel_event: threading.Event | None = None,
    ) -> Review:
        prompt = build_review_prompt(session, plan, utterance)
        response = self._request(prompt, on_partial=None, cancel_event=cancel_event)
        self.last_usage = self.last_usage.add(response.usage)
        return parse_review(response.text)
```

把 `extend_batch` 结尾的 `return [result.utterance]` 替换为：

```python
        self.last_review = None
        try:
            review = self.review_turn(session, plan, result.utterance, cancel_event=cancel_event)
        except (ProviderFailure, ValueError):
            # A failed review must not block the discussion; the turn stands.
            return [result.utterance]
        self.last_review = review
        if review.passed:
            return [result.utterance]
        rewrite_prompt = (
            build_review_prompt(session, plan, result.utterance)
            + f"\n\n质检判定这条发言不合格，具体批评是：{review.criticism}。"
            "请重写这一条发言，只输出一个 JSON 对象，直接解决上述批评，不要解释。\n"
        )
        rewritten = self.generate_turn(
            session.topic,
            selected,
            list(session.sources),
            list(session.utterances),
            TurnSpec(plan.speaker_id, plan.speaker_name, plan.phase, plan.kind_hint),
            on_partial=(lambda text: on_partial(speaker.name, text)) if on_partial else None,
            cancel_event=cancel_event,
            state=state,
            plan=plan,
            extra_prompt=rewrite_prompt,
        )
        return [rewritten.utterance]
```

`generate_turn` 增加一个 `extra_prompt` 形参：签名末尾加 `extra_prompt: str = ""`，并在 `response = self._request(...)` 之前插入：

```python
        if extra_prompt:
            prompt += f"\n{extra_prompt}\n"
```

- [ ] **Step 4: 运行确认通过**

```powershell
& $py -m unittest tests.test_b_integration -v
```

预期：全 PASS。

- [ ] **Step 5: 提交**

```powershell
git add brainstorm/llm.py tests/test_b_integration.py
git commit -m "feat: review each turn and rewrite it once when it does not advance the discussion"
```

---

## Task 7: 三段式长讨论上下文

当前只把最近 12 条纯文本给模型，讨论一长就丢掉开题与用户插话（协议要求插话影响后续所有发言）。

**Files:**
- Modify: `brainstorm/llm.py`（`generate_turn` 的上下文装配）
- Test: `tests/test_b_integration.py`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_b_integration.py` 的 `BIntegrationTests` 类内：

```python
    def test_long_discussion_keeps_topic_opening_and_interjections(self):
        captured = []

        class Event:
            text = '{"content":"后续观点"}'

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
        session = DiscussionSession(topic="社区养老", selected_role_ids=["trend"])
        session.append_utterance(Utterance("moderator", "主持人", "开题：本次只讨论社区场景", ViewpointKind.SUMMARY, "开场", origin="model"))
        session.append_utterance(Utterance("user", "用户", "请优先讨论无障碍体验", ViewpointKind.ASSUMPTION, "用户插话",
                                          origin="user", intent="user_instruction"))
        for index in range(40):
            session.append_utterance(Utterance("trend", "趋势分析师", f"第{index}条填充发言", ViewpointKind.ASSUMPTION, "动态交锋", origin="model"))
        provider.generate_turn("社区养老", [Role("trend", "趋势分析师", "辨别变化", "#2563eb", "关注变化。")],
                               [], list(session.utterances), TurnSpec("trend", "趋势分析师", "动态交锋"))
        prompt = captured[0]
        self.assertIn("开题：本次只讨论社区场景", prompt)
        self.assertIn("请优先讨论无障碍体验", prompt)
        # 近段仍然只取有限条，不能把 40 条全塞进去
        self.assertNotIn("第0条填充发言", prompt)
        self.assertIn("第39条填充发言", prompt)
```

- [ ] **Step 2: 运行确认失败**

```powershell
& $py -m unittest tests.test_b_integration.BIntegrationTests.test_long_discussion_keeps_topic_opening_and_interjections -v
```

预期：FAIL（`开题：…` 不在提示词里，因为它已被 12 条窗口挤掉）。

- [ ] **Step 3: 实现**

`brainstorm/llm.py`，把 `generate_turn` 里的前文装配：

```python
        history_context = "\n".join(
            f"[{item.event_id or '（无编号）'}][{item.phase}][{item.intent}] {item.speaker_name}: {item.content}"
            for item in history[-12:]
        ) or "（尚无前文）"
```

替换为：

```python
        def render(item: Utterance) -> str:
            return (
                f"[{item.event_id or '（无编号）'}][{item.phase}][{item.intent}] "
                f"{item.speaker_name}: {item.content}"
            )

        # Standing section: never truncated, so a long discussion cannot forget
        # the framing or the user's instructions.
        standing = [item for item in history if item.speaker_id in {"moderator", "user"} or item.phase in {"开场", "主持人开题"}]
        standing_ids = {id(item) for item in standing}
        recent = [item for item in history if id(item) not in standing_ids][-RECENT_TURNS:]
        sections = []
        if standing:
            sections.append("常驻（开题与用户插话，永不省略）：\n" + "\n".join(render(item) for item in standing))
        sections.append(f"最近 {RECENT_TURNS} 条：\n" + ("\n".join(render(item) for item in recent) or "（尚无前文）"))
        history_context = "\n\n".join(sections)
```

并在 `llm.py` 顶部常量区加入：

```python
RECENT_TURNS = 24
```

- [ ] **Step 4: 运行确认通过**

```powershell
& $py -m unittest tests.test_b_integration -v
```

预期：全 PASS。

- [ ] **Step 5: 全套 + 提交**

```powershell
& $py -m unittest discover -s tests
git add brainstorm/llm.py tests/test_b_integration.py
git commit -m "feat: keep framing and interjections in context across long discussions"
```

---

## Task 8: 全套回归与用户验收

**Files:** 无代码改动

- [ ] **Step 1: 全套测试**

```powershell
& $py -m unittest discover -s tests
```

预期：Ran 180 项左右 / OK，0 错误 0 失败。卡住则改用 `tools/run_tests_sandboxed.py`。

- [ ] **Step 2: 回归保护（上一轮修复的三条）**

```powershell
& $py -m unittest tests.test_generation_controller.GenerationControllerTests.test_default_discussion_waits_for_click_without_timer tests.test_qt_ui.QtUiTests.test_generation_progress_never_displays_raw_model_payload tests.test_qt_ui.QtUiTests.test_manual_generation_keeps_current_argument_visible -v
```

预期：三条全 PASS。

- [ ] **Step 3: 每次点击的请求次数确认**

真实模型下每次点击应为 **3 次请求**（编排 → 生成 → 质检），质检不合格时为 **4 次**（多一次回炉）。用一次真实运行观察 `session.usage_requests` 的增长是否符合。

- [ ] **Step 4: 真实模型手工验收（**必须由用户执行**）**

跑一场真实 DeepSeek 讨论，逐条点击观察：

1. 发言之间是否真的在互相回应，而不是各说各的。
2. 是否出现"回应 XXX"和主持人介入原因。
3. 是否还会出现"突然变回离线模拟"。
4. 讨论是否比改造前更少重复。
5. 体感上每条发言等待多久（编排与质检会让每次点击变慢，这是已知代价）。

**这一步的结论只能由用户给出。实施者不得以自己的观察代替，也不得宣称"讨论变深刻了"。**

- [ ] **Step 5: 提交**

```powershell
git add -A
git commit -m "test: verify conversation model phases 3-4"
```

---

## 收尾：更新记忆文件

在 `PROJECT_MEMORY.md` 第 12 节把第三、四期的完成情况写清，特别是：

- 每次点击现在会发 3～4 次模型请求，这是有效性换来的已知代价；
- **后台预取与结束总结多遍仍未做**，以及为什么延后（只影响等待时间，不影响有效性）；
- 真实讨论手感仍待用户验收。

---

## Self-Review 记录

**Spec 覆盖检查**（对照 `2026-10-12-conversation-model-design.md`）：

| Spec 章节 | 覆盖任务 |
| --- | --- |
| §4 调用 A 编排（关键问题／发言人／必须回答／避免重复／介入／状态刷新） | Task 4、Task 5 |
| §4 调用 B 生成（按编排指令） | Task 5 |
| §4 调用 C 质检（重复／回避／编造） | Task 6 |
| §4 调用 D 重写（最多一次） | Task 6 |
| §5.4.1 格式错误回灌重试 | Task 2 |
| §5.4.2 重复检测只标记不删除 | Task 3 |
| §5.4.3 三段式长讨论上下文 | Task 7 |
| §7 编排失败回退本地计划 | Task 5 |
| §7 质检失败视为通过并继续 | Task 6 |
| §9 明确不包含后台预取 | 本计划延后说明 |
| §9 明确不包含多候选择优 | 未实现，符合 §9 |

**已知未覆盖项（有意延后）：** 后台预取与并发约束（§4 末段）、结束总结多遍成稿（§5.4.5）。两者都**不影响讨论过程的有效性**，前者只影响等待时间，后者影响最终档案质量。延后决定已在本计划开头写明，将来单独出计划。

**类型一致性检查：** `TurnPlan` 在 Task 4 增加 `must_answer`／`avoid`／`key_question` 三个带默认值的字段，Task 5、Task 6 按同名使用；`OrchestrationRefresh` 在 Task 4 定义并在 Task 5 的控制器代码与测试中按 `consensus`／`conflicts`／`unresolved` 使用；`Review` 在 Task 4 定义（字段 `passed`／`repeats`／`avoided`／`fabricated`，属性 `criticism`），Task 6 按同名使用；`parse_orchestration` 返回 `(TurnPlan, OrchestrationRefresh)` 二元组，Task 5 按二元组解包；`parse_review` 返回 `Review`，Task 6 按 `Review` 使用。`provider.last_state_refresh` 在 Task 5 定义、Task 5 控制器读取并置空；`provider.last_review` 在 Task 6 定义。
