# 九人圆桌混合讨论模式 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有按模板追加的圆桌播放升级为可无限继续、状态触发整理、支持多次回应和立场变化、可恢复保存的混合讨论。

**Architecture:** 保留 `Utterance` 作为 UI 和导出的兼容记录类型，在其上增加事件元数据；在 `DiscussionSession` 中增加可重建的讨论状态快照。离线 provider 和可选模型 provider 通过统一的批次接口生成追加发言，控制器在 GUI 线程应用批次、逐事件保存并驱动播放；状态监测器决定主持人何时整理，Qt 页面只消费状态信号，不自行推断讨论逻辑。

**Tech Stack:** Python 3.12, PySide6, `unittest`, JSON 本地存储, PyInstaller one-folder。

---

## 文件边界

- `brainstorm/models.py`：事件元数据、立场变化、讨论状态和会话阶段的领域类型。
- `brainstorm/engine.py`：离线讨论状态分析、候选回应选择、状态触发的主持人整理和追加批次。
- `brainstorm/llm.py`：可选模型 provider 的批次上下文、插话上下文和结构化字段解析；继续沿用安全回退。
- `brainstorm/session_controller.py`：批次异步执行、取消、逐事件保存、状态信号和用户控制。
- `brainstorm/playback.py`：无限 live 播放、追加批次边界和暂停/恢复语义。
- `brainstorm/storage.py`：新增字段的 JSON 序列化、兼容旧历史和状态重建。
- `brainstorm/export.py`：完整事件元数据、状态、立场轨迹、分歧和未验证标记。
- `brainstorm/qt_app.py`：圆桌阶段 HUD、共识/分歧/未回答状态区、回应标签、立场变化和总结页。
- `tests/test_engine.py`：状态分析、动态回应、状态触发和立场变化的单元测试。
- `tests/test_generation_controller.py`：异步批次、插话优先、取消、逐事件保存和失败回退测试。
- `tests/test_persistence_playback.py`：新 schema、旧历史兼容、状态恢复和导出字段测试。
- `tests/test_qt_ui.py`：状态区、回应标签、立场轨迹和总结页 smoke 测试。
- `README.md`、`nine-roundtable-stages.md`：用户可见行为和阶段说明。

## Task 1: 建立讨论事件与状态模型

**Files:**
- Modify: `brainstorm/models.py`
- Modify: `brainstorm/storage.py`
- Test: `tests/test_persistence_playback.py`
- Test: `tests/test_engine.py`

- [ ] **Step 1: 写失败测试，锁定新字段的默认值和旧记录兼容。**

```python
def test_new_discussion_metadata_round_trips(self):
    session = MockDiscussionProvider().discuss("无障碍服务", DEFAULT_ROLES[:3])
    item = session.utterances[1]
    self.assertTrue(item.event_id)
    self.assertEqual(item.sequence, 1)
    self.assertEqual(item.intent, "initial")
    self.assertEqual(item.verification, "unverified")
    self.assertEqual(session.phase, "首轮观点")
    self.assertEqual(session.discussion_state.unresolved_questions, [])
    restored = session_from_dict(session_to_dict(session))
    self.assertEqual(restored.utterances[1].event_id, item.event_id)
    self.assertEqual(restored.discussion_state.active_thread, session.discussion_state.active_thread)

def test_legacy_utterance_defaults_to_safe_event_metadata(self):
    restored = session_from_dict({
        "schema_version": SCHEMA_VERSION,
        "topic": "旧记录",
        "created_at": "2030-01-01T12:00:00",
        "utterances": [{
            "speaker_id": "moderator", "speaker_name": "主持人",
            "content": "开场", "kind": "总结", "phase": "开场",
        }],
    })
    self.assertEqual(restored.utterances[0].sequence, 0)
    self.assertEqual(restored.utterances[0].verification, "unverified")
    self.assertEqual(restored.phase, "开题")
```

- [ ] **Step 2: 运行失败测试，确认当前模型没有这些字段。**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path '.qt-build-runtime').Path
$py='C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m unittest tests.test_engine tests.test_persistence_playback -v
```

Expected: FAIL with missing `event_id`/`discussion_state` attributes.

- [ ] **Step 3: 增加结构化类型并保持构造兼容。**

在 `models.py` 中增加：

```python
@dataclass(frozen=True)
class StanceChange:
    before: str
    after: str
    reason: str
    triggered_by: list[str] = field(default_factory=list)

@dataclass
class DiscussionState:
    consensus: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    duplicate_count: int = 0
    new_information_density: float = 1.0
    active_thread: str = ""
    host_intervention_reason: str = ""
    role_stances: dict[str, str] = field(default_factory=dict)
    pending_user_interjection: str = ""

@dataclass(frozen=True)
class Utterance:
    # existing fields remain first for positional compatibility
    speaker_id: str
    speaker_name: str
    content: str
    kind: ViewpointKind
    phase: str
    replies_to: Optional[str] = None
    simulated: bool = True
    origin: str = ""
    event_id: str = ""
    sequence: int = -1
    intent: str = "initial"
    verification: str = "unverified"
    stance_change: StanceChange | None = None
    duplicate: bool = False
```

`DiscussionSession` 增加 `phase`、`run_state`、`discussion_state`，并提供 `next_sequence()` 与 `append_utterance()`：后者负责补齐 event id、sequence 和默认来源，避免 provider 和 controller 各自维护顺序。

- [ ] **Step 4: 更新 JSON schema。**

在 `storage.py` 将 `SCHEMA_VERSION` 提升到 6；`session_to_dict()` 写入阶段、运行状态、状态快照和新增事件字段。`session_from_dict()` 对缺失字段使用安全默认值，对旧事件按列表顺序补 sequence 和生成稳定 event id；未来 schema 仍然拒绝。`StanceChange` 和 `DiscussionState` 使用显式转换，不直接把枚举或 datetime 交给 JSON。

- [ ] **Step 5: 运行测试确认新旧数据都通过。**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path '.qt-build-runtime').Path
$py='C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m unittest tests.test_engine tests.test_persistence_playback -v
```

Expected: 新测试和现有持久化测试全部 PASS。

## Task 2: 实现状态分析和动态离线讨论

**Files:**
- Modify: `brainstorm/engine.py`
- Modify: `brainstorm/models.py`
- Test: `tests/test_engine.py`

- [ ] **Step 1: 写失败测试，验证状态分析和状态触发。**

```python
def test_state_analyzer_tracks_consensus_conflict_and_unresolved_question(self):
    session = MockDiscussionProvider().discuss("社区养老", DEFAULT_ROLES)
    state = MockDiscussionProvider.analyze_state(session)
    self.assertTrue(state.consensus)
    self.assertTrue(state.conflicts)
    self.assertTrue(state.unresolved_questions)
    self.assertGreaterEqual(state.duplicate_count, 0)

def test_extend_marks_reply_intent_and_can_change_stance(self):
    provider = MockDiscussionProvider()
    session = provider.discuss("社区养老", DEFAULT_ROLES)
    added = provider.extend(session, 1)
    self.assertTrue(any(item.replies_to for item in added))
    self.assertTrue(any(item.intent in {"support", "challenge", "question", "elaborate"} for item in added))
    self.assertTrue(any(item.stance_change is not None for item in added))
    self.assertEqual(session.utterances[-1].speaker_id, "moderator")
    self.assertIn(session.phase, {"动态交锋", "状态整理"})

def test_extend_keeps_user_interjection_as_highest_priority_context(self):
    provider = MockDiscussionProvider()
    session = provider.discuss("数字服务", DEFAULT_ROLES[:4])
    session.append_utterance(Utterance("user", "用户", "优先讨论无障碍体验", ViewpointKind.ASSUMPTION, "用户插话", simulated=False, origin="user", intent="user_instruction"))
    added = provider.extend(session, 1)
    self.assertTrue(any("无障碍体验" in item.content for item in added))
    self.assertEqual(session.discussion_state.pending_user_interjection, "")
```

- [ ] **Step 2: 运行测试确认当前固定模板无法满足意图、立场变化和状态快照要求。**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path '.qt-build-runtime').Path
$py='C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m unittest tests.test_engine -v
```

Expected: the new assertions fail while the existing fixed-batch tests remain visible.

- [ ] **Step 3: 添加确定性的 `analyze_state()`。**

扫描最近事件，按规范化文本去重；将主持人整理中的“共识/分歧/未回答”提取为状态，将连续同类观点归入重复计数，将最近角色观点映射到 `role_stances`。没有足够证据时保留空列表，不把普通模拟句子强行标为共识。

`should_intervene(state, recent_events)` 返回 `(bool, reason)`，只有满足以下之一才触发整理：重复率高于最近新观点率、存在未回答问题且连续两条事件未回应、最近批次无有效新角色、或冲突线程出现双方交锋后需要汇总。单个批次仍最多产生 8 条事件，限制只保护 UI，不是总轮数限制。

- [ ] **Step 4: 重写 `MockDiscussionProvider.extend()` 的批次选择。**

保留 `extend(session, batch_index)` 的兼容签名，内部先调用 `analyze_state()`，再从已选角色中轮换候选。每条新 `Utterance` 写入 `replies_to`、`intent`、`verification="unverified"` 和可选 `StanceChange`；回应用户插话的第一条内容必须包含插话主题。状态触发时才插入主持人 `phase_summary`，并把 `host_intervention_reason` 写入事件元数据和快照；没有触发时批次不插入主持人收束句。追加后调用 `session.append_utterance()` 和 `session.rebuild_state()`。

- [ ] **Step 5: 更新机会档案和测试。**

`_refresh_opportunity()` 保留现有字段，同时把 `state.consensus`、`state.conflicts`、`state.unresolved_questions` 作为后续总结输入；只使用事件内容，不把用户插话计入角色统计。运行引擎测试，确认九角色轮换、无限批次、用户不被冒充和新增状态测试全部 PASS。

## Task 3: 让模型 provider 共用批次上下文并安全回退

**Files:**
- Modify: `brainstorm/llm.py`
- Modify: `brainstorm/engine.py`
- Test: `tests/test_b_integration.py`

- [ ] **Step 1: 写 provider contract 测试。**

使用可注入 fake client，验证继续讨论请求包含最近事件、当前状态、用户插话和“未核验”约束；返回 JSON 中的 `intent`、`replies_to` 和 `stance_change` 能保存；模型错误只产生安全失败，不泄露异常内容。

- [ ] **Step 2: 扩展模型 JSON 解析。**

在 `AnthropicDiscussionProvider._parse()` 支持 `intent` 和可选 `stance_change` 对象；`replies_to` 只接受历史中存在的 event id 或 speaker id，并转换为实际 event id。所有模型事件继续使用 `origin="model"`、`verification="unverified"`。非法结构继续抛出 `ProviderFailure`，由控制器执行离线回退。

- [ ] **Step 3: 增加 `extend_batch()`。**

新增方法签名：

```python
def extend_batch(
    self,
    session: DiscussionSession,
    state: DiscussionState,
    *,
    cancel_event: threading.Event | None = None,
    on_partial: Callable[[str, str], None] | None = None,
) -> list[Utterance]:
    ...
```

方法只发送最近 12 条事件、结构化状态、用户插话和角色职责；每个请求只生成一条事件，遇到取消立即抛出 `GenerationCancelled`。生成失败由调用方区分“取消”和“可回退错误”。

- [ ] **Step 4: 保持旧 provider 行为并运行集成测试。**

初始 `discuss()` 继续生成开题和首轮观点；`extend_batch()` 不改变旧历史格式。运行：

```powershell
$env:PYTHONPATH=(Resolve-Path '.qt-build-runtime').Path
$py='C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m unittest tests.test_b_integration -v
```

Expected: 现有 13 项模型/RSS 集成测试和新增批次测试全部 PASS。

## Task 4: 控制器接入无限调度、状态触发和逐事件保存

**Files:**
- Modify: `brainstorm/session_controller.py`
- Modify: `brainstorm/playback.py`
- Modify: `brainstorm/storage.py`
- Test: `tests/test_generation_controller.py`
- Test: `tests/test_persistence_playback.py`

- [ ] **Step 1: 写失败测试，验证用户可连续追加、插话优先、每批保存和取消。**

覆盖以下行为：

```python
def test_interjection_is_consumed_before_next_batch(self):
    controller = self.track(SessionController(store=SessionStore(self._history_tmp)))
    controller.start("无障碍服务", [ROLE])
    process_until(lambda: controller.session is not None)
    controller.add_interjection("优先讨论低视力用户")
    controller.extend_discussion()
    self.assertTrue(any("低视力用户" in item.content for item in controller.session.utterances))

def test_each_added_batch_is_persisted(self):
    controller = self.track(SessionController(store=SessionStore(self._history_tmp)))
    controller.start("保存测试", [ROLE])
    process_until(lambda: controller.session is not None)
    before = len(list(self._history_tmp.glob("*.json")))
    controller.extend_discussion()
    after = len(list(self._history_tmp.glob("*.json")))
    self.assertGreaterEqual(after, before)
    self.assertEqual(SessionStore(self._history_tmp).list_sessions()[0].utterances[-1].event_id, controller.session.utterances[-1].event_id)
```

- [ ] **Step 2: 运行新增 controller 测试，确认当前同步追加和缺少状态信号。**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path '.qt-build-runtime').Path
$env:QT_QPA_PLATFORM='offscreen'
$py='C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m unittest tests.test_generation_controller -v
```

Expected: new async/state assertions fail.

- [ ] **Step 3: 增加批次 worker 和状态信号。**

扩展现有 `_GenerationWorker` 或新增 `_BatchWorker`，在后台调用模型 `extend_batch()`；离线 provider 生成的批次也通过同一 controller 应用路径。增加 `discussion_state_changed`、`phase_changed`、`batch_started` 和 `batch_finished` 信号。GUI 线程收到完整批次后按顺序调用 `session.append_utterance()`、更新 `playback`，每条事件后 `store.save(session)`，再发出状态和播放信号。

- [ ] **Step 4: 明确暂停、取消、结束和回退。**

暂停只停止播放 timer 和待处理批次调度，不删除已保存事件；取消使 token 失效，迟到结果不得写入当前会话；模型错误重试一次，仍失败时写入 `system_notice` 并用离线 provider 继续；用户结束时取消 worker、保留已展示/已保存事件，刷新机会档案和状态快照后保存并发出 `completed`。

- [ ] **Step 5: 运行 controller、playback 和持久化测试。**

```powershell
$env:PYTHONPATH=(Resolve-Path '.qt-build-runtime').Path
$env:QT_QPA_PLATFORM='offscreen'
$py='C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m unittest tests.test_generation_controller tests.test_persistence_playback -v
```

Expected: 原有 live 播放、取消、历史和新增的状态/保存测试全部 PASS。

## Task 5: 圆桌状态 UI 与总结页

**Files:**
- Modify: `brainstorm/qt_app.py`
- Modify: `brainstorm/qt_theme.py`
- Modify: `brainstorm/roundtable.py`
- Modify: `brainstorm/export.py`
- Test: `tests/test_qt_ui.py`

- [ ] **Step 1: 写 Qt smoke 测试。**

```python
def test_roundtable_shows_live_discussion_state(self):
    session = MockDiscussionProvider().discuss("社区养老", DEFAULT_ROLES)
    page = RoundtablePage(self.controller)
    page.load_session(session)
    self.assertTrue(page.findChild(QLabel, "discussionStateLabel"))
    page._state_changed(session.discussion_state)
    self.assertIn("共识", page.findChild(QLabel, "discussionStateLabel").text())

def test_summary_page_shows_unresolved_conflicts_and_stance_changes(self):
    session = MockDiscussionProvider().discuss("社区养老", DEFAULT_ROLES)
    page = SummaryPage(session)
    text = "\n".join(label.text() for label in page.findChildren(QLabel))
    self.assertIn("未解决分歧", text)
    self.assertIn("立场轨迹", text)
```

- [ ] **Step 2: 实现最小可读状态区。**

圆桌 HUD 增加阶段和运行状态；在记录抽屉或其上方增加共识、分歧、未回答问题三个紧凑区块。每条记录显示回应对象、意图、来源和“改变立场”标记；主持人整理显示介入原因。状态文本使用现有森林绿、暗金和暖白主题，不新增白色默认面板。

- [ ] **Step 3: 接收 controller 状态信号。**

`RoundtablePage` 只订阅 `discussion_state_changed` 和 `phase_changed`，更新标签、圆桌状态和当前字幕；不在 UI 线程分析事件。用户插话后显示“已加入下一批回应队列”，无法生成时显示“待处理”，不伪造回应。

- [ ] **Step 4: 扩展总结页和导出。**

`SummaryPage.set_session()` 增加共识、主要分歧、未回答问题、立场轨迹和来源/核验状态；空列表显示“暂无记录”。`export_markdown()` 和 JSON 继续输出完整事件元数据以及这些状态，历史页面加载时不触发生成。

- [ ] **Step 5: 运行 Qt 测试和布局验证。**

```powershell
$env:PYTHONPATH=(Resolve-Path '.qt-build-runtime').Path
$env:QT_QPA_PLATFORM='offscreen'
$py='C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m unittest tests.test_qt_ui -v
& $py tools/verify_ui.py artifacts/ui-verification-discussion
```

Expected: Qt tests pass; `layout.json` reports all four target sizes with actual page sizes equal to requested sizes and visible primary controls.

## Task 6: 文档、全量回归和桌面包验证

**Files:**
- Modify: `README.md`
- Modify: `nine-roundtable-stages.md`
- Run: `python -m compileall`, full unittest, PyInstaller Qt spec

- [ ] **Step 1: 更新产品说明。**

说明无限讨论、状态触发主持人整理、角色多次发言、回应/反驳/追问、可改变立场、用户插话优先、手动结束总结、离线/模型来源和未核验约束；不要把模拟内容写成真实模型结果。

- [ ] **Step 2: 运行完整静态和行为验证。**

```powershell
$env:PYTHONPATH=(Resolve-Path '.qt-build-runtime').Path
$env:QT_QPA_PLATFORM='offscreen'
$py='C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m compileall -q brainstorm app.py tests
& $py -m unittest discover -s tests -v
```

Expected: compileall exit 0 and unittest reports 0 failures.

- [ ] **Step 3: 构建隔离的 Qt one-folder 包。**

```powershell
$env:PYTHONPATH=(Resolve-Path '.qt-build-runtime').Path
$py='C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m PyInstaller --noconfirm --clean --windowed --distpath dist-discussion --workpath build-discussion '九人圆桌-Qt.spec'
```

Expected: `dist-discussion\九人圆桌-Qt\九人圆桌-Qt.exe` exists and the assets directory is present.

- [ ] **Step 4: 启动包并做最小人工流程验证。**

启动隔离包，输入主题并开始；确认首轮后可以继续多批、同一角色可重复发言、插话进入下一批、暂停/继续不改变已保存记录，点击“结束并总结”能打开包含分歧和立场轨迹的总结页。验证完成后只报告实际可见结果，不覆盖桌面现有最新版。

- [ ] **Step 5: 记录最终证据。**

保存全量测试输出、`layout.json` 和构建产物路径；检查 `git status`（若目录仍不是 Git 仓库则明确记录，不能假称已提交）。

## 计划自检

- 设计中的无限讨论、状态触发、混合点名、多次发言、立场变化、用户插话、事件流、异常恢复、总结和导出分别由 Task 1–5 覆盖。
- 旧历史兼容由 Task 1 和 Task 4 的 schema 测试覆盖；真实模型安全标记和回退由 Task 3 覆盖。
- 没有固定总轮数；单批 8 条只作为 UI 保护，并在 Task 2 和 Task 4 中明确。
- 计划没有加入自动 RSS、事实核验、语音、复杂动效或新的安装器流程。
- 已检查计划没有未定义的占位步骤或空泛要求；所有代码步骤均包含接口、测试或精确命令。
