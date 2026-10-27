# 观点讨论分区（说法体检单）设计

日期：2026-10-27
状态：已实现

## 用户要什么

> 「我让重新加的另一个对某观点或者某说法的讨论去哪了，单开一个板块好吗」

第三个分区：不听商业痛点，不看社会事件，只拆**一句话**——某个观点、某个说法、"人家都说……"。

## 和前两个分区的差别

| | 商业痛点 | 事件讨论 | 观点讨论 |
| --- | --- | --- | --- |
| 输入 | 一个痛点／需求 | 一件发生的事 | 一句说法 |
| 八个人的身份 | 职业视角 | 八卦性格 | 拆解位置 |
| 核心问题 | 这值不值得做 | 这到底怎么回事 | 这话站不站得住 |
| 产出 | 机会档案 | 吃瓜纪要 | 说法体检单 |
| 阴阳两面 | 无 | 有（情绪账本） | 无 |

观点讨论**故意不做阴阳两面**：拆一个说法需要的是稳定的方法论位置，不是性格戏。人物靠 `voice` 区分，不靠翻脸。

## 八个席位

| id | 名字 | 位置 | 口吻 |
| --- | --- | --- | --- |
| claim_advocate | 主张者 | 把说法讲到最强 | 按这个说法……讲完就停 |
| claim_skeptic | 挑刺者 | 找反例、找偷换 | 那……呢？一次咬一个点 |
| claim_data | 数据员 | 要数、要口径 | 多少、哪年、谁统计的 |
| claim_insider | 行内人 | 一线实际怎么运转 | 我们那边…… |
| claim_boundary | 条件派 | 划前提与边界 | 在……的前提下，只有……才 |
| claim_motive | 动机派 | 谁在说、图什么 | 这么说对他有什么好处 |
| claim_analogy | 类比手 | 拿别的领域对照 | 这就像…… |
| claim_layman | 外行 | 代表听不懂的人 | 这啥意思，跟我有啥关系 |

## 五层往下走（`brainstorm/agenda.py` 的 `CLAIM_LAYERS`）

1. 这说法到底在说什么
2. 它凭什么站得住
3. 什么情况下不成立
4. 谁在这么说、图什么
5. 能信到什么程度、怎么用

每层 6 条发言，换层时主持人一句话带过。上限由层数决定，不是轮次表。

## 硬规矩

- **不许编数**：要证据就说清缺什么（多少／哪年／谁统计／样本是谁），没有就说没有。
- 反例要具体：哪一类人、哪种情况。
- 不许把「我猜」「我听说」写成已证实。
- 不喊口号、不写「我们应该」。

## 落点

- `brainstorm/roles.py`：`CLAIM_ROLES`（8 个 `Role`，含 `voice`）、`CLAIM_ROLE_IDS`、`CLAIM_ROLE_BY_ID`；`ROLES_BY_MODE` / `MODE_LABELS` / `SECTION_TEXT` / `mode_for_roles` 增加 `claim`。
- `brainstorm/agenda.py`：`CLAIM_LAYERS` + 五层的追问提示（并入 `LAYER_QUESTIONS`）。
- `brainstorm/llm.py`：`_generate_turn_result` 的 `claim` 规则分支；`spec.final` 时把 `opportunity` 字段映射成说法体检单。
- `brainstorm/engine.py`：`_claim_opening` / `_claim_extend`（离线演示也要演对方法：先讲最强版本，再给反例、要数、划边界）。
- `brainstorm/qt_app.py`：大厅第三个按钮；徽标「说法桌 · 观点讨论」；`_quick` 的默认四人。
- `assets/avatars/claim_*.png|svg`：8 张头像。
- `docs/使用说明-详细版.md`：第四节新增「第三个分区：观点讨论」。

## 不做什么

- 不新增存储字段（`mode` 已是字符串；`mode_for_roles` 按席位推断，旧存档不受影响）。
- 不给观点讨论加阴阳面／情绪账本。
- 不改商业痛点与事件讨论的既有提示词文本（已验收的手感不重开）。

## 验证

- `tests/test_claim_section.py` 12 项：席位与口吻、名字不撞车、`mode_for_roles`、`SECTION_TEXT` 键齐、五层推进、离线的开场/续轮/卡片、提示词分支、存档往返。
- `tests/test_qt_ui.py` 新增 `test_lobby_has_a_third_table_for_a_claim`。
- 全量 337 项通过。
