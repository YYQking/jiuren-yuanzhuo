# 九人圆桌对话模型（第五批）逻辑修复计划

**Goal:** 修掉对话模型里五个可复现的逻辑缺陷——主持人会霸占圆桌、模型选的发言人绕开公平性上限、被指派回应的对象看不见原文、用户插话永久留在提示词里、主持人改成角色后阶段标签错乱——并把"质检回炉"这条路变成看得见的。

**Tech Stack:** Python 3、unittest（本项目**不用 pytest**）、PySide6/Qt、PyInstaller 文件夹式打包。

**前置状态：** 第一至四期已完成，`conversation-model` 分支，`a87c776`，226 项测试通过。

**不在本期范围：** 后台预取、结束总结多遍成稿、存储 schema 升级（保持 v6）、热点与新闻、LLM 失败后的重试与熔断策略。

---

## 全局约定

**Python 解释器：**

```
C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
```

**每个新 shell 先设置环境：**

```powershell
$env:PYTHONPATH=(Resolve-Path '.').Path + ';' + (Resolve-Path '.qt-build-runtime').Path
$env:QT_QPA_PLATFORM='offscreen'
```

**全量测试：**

```powershell
& $py -m unittest discover -s tests
```

**每个缺陷都先跑出失败证据再改。** 下面是五项已验证的缺陷与对应修复。

---

## Task A：主持人冷却 ✅

**缺陷（已复现）：** `detect_intervention` 只看角色发言（`_role_utterances` 把主持人排除），所以主持人自己的收束**不改变任何触发条件**。触发一旦成立就永远成立：

```
intervention: (True, '发言集中在少数角色，讨论冷场')
plan 1: moderator | 发言集中在少数角色，讨论冷场
plan 2: moderator | 发言集中在少数角色，讨论冷场
plan 3: moderator | 发言集中在少数角色，讨论冷场
```

**修复：**
- `turn_planner.MODERATOR_COOLDOWN_TURNS = 4`；新增 `moderator_available(session)`：主持人从未发言 → 可用；否则要求距上次发言已过 ≥4 条**角色**发言（用户插话不计入，不会把主持人冻住）。
- `plan_turn` 的介入分支加门控。**`detect_intervention` 保持只报证据**，因为 `session_controller` 用它填 UI 的"介入原因"，所以既有的 5 个触发条件测试与 `test_moderator_batch_records_intervention_reason` 都不用改。
- `parse_orchestration`：冷却期内模型仍选 moderator → 抛 `ValueError` → 调用方退回本地角色计划。
- 顺带修掉优先级矛盾：冷却生效后「优先回应用户插话」（rule 1）恢复最高优先级。

**修复后：**
```
plan before host speaks: moderator
plan after  host speaks: builder (was moderator forever)
```

---

## Task B：模型选的发言人也要过公平性检查 ✅

**缺陷（已复现）：** `parse_orchestration` 只替换发言人，从不调用 `_guard`，所以"同一角色不得连续 3 条 / 最近 6 条最多 2 条"只保护兜底路径。让编排器每次都选 `trend`：

```
actual speakers: ['trend', 'trend', 'trend', 'trend', 'trend', 'trend']
```

**修复：**
- `turn_planner.enforce_fairness(plan, session, candidates)` 公开包装 `_guard`（`_guard` 保持私有）。
- `llm.extend_batch` 在编排成功后、且不是主持人时调用它。`_guard` 只在硬上限被突破时换人。
- `build_orchestration_prompt` 增加第 6 条硬规则与「发言权分配事实」（最近 6 条角色发言的发言人及条数），先让模型自己守规矩。

**修复后：** `['industry', 'technology', 'need', 'trend', 'bystander', 'trend']`

---

## Task C：主持人→角色改写时重置阶段语义 ✅

**缺陷（已复现）：** `replace(local, ...)` 保留了主持人计划的语义：

```
model overrode host -> phase: '状态整理' | moderator: False | kind_hint: '总结' | intent: 'synthesize'
```

**修复：** `parse_orchestration` 的 `else` 分支，若 `local.moderator` 为真则把 `phase` 重置为 `动态交锋`、`intent` 为 `elaborate`、`kind_hint` 为 `假设`；本地计划本来就是角色时保持原样。

**修复后：** `overridden phase: '动态交锋' kind: '假设'`

---

## Task D：用户插话的"有效期"只留一个定义 ✅

**缺陷（已复现）：** `rebuild_state()` 把最近一条用户插话写进 `pending_user_interjection` 且**从不清除**，而调度器 6 条之后就过期了。第 10 条时：

```
planner still prioritising the interjection? no
but the prompt would still carry: '请优先讨论无障碍体验'
```

**修复：**
- `models.USER_INTERJECTION_WINDOW = 6` 与 `DiscussionSession.pending_interjection(window=0)`：最近一条未被 `replies_to` 引用、且未超出窗口的 `user_instruction`。
- `turn_planner.USER_WINDOW` 改为引用它，rule 1 用同一个方法；`rebuild_state()` 由它派生。
- 常量放 `models.py` 是为了避免 `turn_planner → models` 的反向导入（`turn_planner` 已 import `models`）。`engine.py` 里那句显式清空保留不动。

**修复后：** `pending interjection at turn 12: '' (was the stale text)`

---

## Task E：让角色看得见它在回应什么 ✅

**缺陷（已复现）：** 生成提示词只渲染最近 12 条，被指派对象从完整历史里找却只打印编号和名字。21 条历史时：

```
target event id present?  True
target CONTENT present?   False
本地编排要求：本次发言必须回应 [event-000000] 趋势分析师，并且必须回答：…
```

**修复：**
- 指令行改为带原文引用：`本次发言必须回应 [event-000000] 趋势分析师：「<原文截断 240 字>」`。
- 新增 `_render_opening_positions()`：每个角色一条"最初立场"（截断 120 字，最多 9 条），**仅当该条已滑出最近 12 条窗口时**加入；与最近窗口、以及被指令引用的那条按 `event_id` 去重。
- `RECENT_TURNS` 从写死的 `12` 提为常量。
- 这是计划里挂着的"三段式长讨论上下文"的最省做法：**不增加任何模型请求**。

**修复后：** `target CONTENT present? True`

---

## Task F：编排缺字段不再丢掉整次编排 ✅

**缺陷：** `must_answer` 缺失即抛错，于是模型选的发言人**和**同一次请求里的状态刷新一起被丢弃。

**修复：** 空白 `must_answer` 记为空串（生成提示词本来就有 `plan.must_answer or plan.reason` 兜底）；仍然抛错的是 JSON 不可解析、`speaker_id` 缺失或不在名单、冷却期内选主持人。

**契约变化：** `test_missing_must_answer_raises` 改名为 `test_missing_must_answer_keeps_the_speaker_and_the_state_refresh`，有意为之。

---

## Task G：主持人也过质检 + 质检痕迹可见 ✅

**缺陷：** `if plan.moderator: return [result.utterance]` 让主持人收束跳过质检——最可能变成"复述"的那一条反而是唯一不检查的；而且"质检打回重写"这条路在界面上完全看不见，第四期的记录里它在真实模型上从未触发过。

**修复：**
- 去掉提前返回，主持人走同一套 review → 一次回炉。
- `Utterance.review_note`（默认 `""`）；回炉成功时写入批评。`storage.py` 往返该字段，**`SCHEMA_VERSION` 保持 6**（旧文件缺键即空串）。
- `qt_app._transcript_line` 追加 ` · 质检重写：<批评>`，只出现在「完整记录」，不挤占发言卡片。

**修复前证据：** `git show HEAD:brainstorm/llm.py` 里存在 `if plan.moderator: return [result.utterance]`；`git show HEAD:brainstorm/models.py` 里没有 `review_note`。

---

## 验收结果

| 项 | 结果 |
| --- | --- |
| 全量测试 | 226 → **248** 项，全绿 |
| 五个缺陷复现脚本 | 修复后全部转为正确行为（见各 Task 的"修复后"） |
| 公开接口 | 新增 `moderator_available`、`enforce_fairness`、`DiscussionSession.pending_interjection`、`Utterance.review_note`；`TurnPlan` 字段不变；`detect_intervention` 签名语义不变 |
| 数据结构 | `Utterance` 多一个带默认值的字段，存储版本不变 |
| 真实模型跑测 | 见 `PROJECT_MEMORY.md` 的第五批记录 |

**仍未验证：** 质检回炉在真实模型上是否触发、是否提升质量。本批只保证它可见，不宣称它有效。
