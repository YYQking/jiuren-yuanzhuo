# 九人圆桌 · Agent 项目记忆与交接

更新日期：2026-10-12（Asia/Shanghai）。本文件结合用户确认、源码检查与本次会话实际验证整理。**先读本文件，再读 `AGENT_HANDOFF.md` 和相关设计文档。**

## 1. 一分钟了解项目

这是中文 Windows 桌面头脑风暴软件：用户输入主题，九个固定社会/职业视角讨论，主持人负责开题和整理，用户手动结束后打开总结与机会档案。

项目根目录：`C:\Users\14726\Desktop\头脑风暴`。

技术栈：Python、PySide6/Qt、自绘圆桌与内置 SVG 头像、JSON 本地存储、Markdown/JSON 导出、PyInstaller 文件夹式打包。

当前桌面交付：

- 程序文件夹：`C:\Users\14726\Desktop\九人圆桌热点版`。
- 程序入口：该文件夹中的 `九人圆桌.exe`。
- 桌面快捷方式：`九人圆桌热点版.lnk`。
- 分享包：`C:\Users\14726\Desktop\九人圆桌最新版-可直接发送-OpenAI版.zip`。
- 最新修复构建：项目内 `dist-manual\九人圆桌-Qt`，构建目录 `build-manual`。

用户已授权本机 DeepSeek 配置并成功完成一次真实聊天接口连通测试。此后又修复了原始 JSON 显示和自动切换发言的问题，重新更新了桌面版与分享包。

## 2. 用户习惯与最新要求（重要）

- 用户希望自主连续实施并验证，不反复问常规权限或实现选择；实际工具权限限制仍须遵守。
- 沟通用中文、少术语，讲清正在做什么；用户多次询问“在做吗”“咋回事”，长任务需要简短进度反馈。
- 桌面保留清楚的一套最新版，不制造一堆难辨认的备份、旧发送包。
- **最新明确要求：由用户点击才显示下一条发言。用户没有看完时不能自动换人、自动替换观点。**
- 无限讨论与自动阶段安排不等于自动播放。阶段与角色调度可以由系统安排，展示推进由用户点击控制。
- 用户反馈截图中的所谓“乱码”是 `{"content":...,"kind":...,"replies_to":...}` 等内部 JSON 被显示在气泡中，并非截图证明了中文编码错误。
- 本文件不包含任何 API Key；后续 Agent 不要从聊天历史复制密钥到文档、脚本、项目、日志或分享包。

## 3. 产品及 UI 已确认方向

主场景是沉浸式游戏/贵宾牌室风格，圆桌是主角。用户否定了旧 Tkinter 表单加绿色圆桌的方案。

- 深森林绿、炭黑、胡桃木、暗金与暖白文字；圆滑统一，不能出现白色默认控件或后台管理式卡片堆积。
- 主题大厅 → 圆桌主场景 → 独立机会档案总结页；默认全屏无边框，提供窗口化、退出及 Esc 操作。
- 俯视椭圆桌、九个固定席位、独立主持人；原创 SVG 头像；当前角色高亮。
- 克制 HUD、当前气泡、字幕、右侧完整记录抽屉；全文、来源、历史和导出可追溯。
- 适配 1366×768、1920×1080 及 Windows 缩放；不要以主窗口能打开代替完整视觉验收。
- 无授权音频时静默，不能假装实现角色语音或完整环境音。

详细原始需求保存在 `AGENT_HANDOFF.md`。该文件主要记录设计目标，不能当作全部功能已验收的证明。

## 4. 九人讨论协议

九人是同一个模型服务扮演的固定角色视角，**不是九个真实人物，也不是九个独立模型账户**。主持人不占九席。

| ID | 固定角色 |
| --- | --- |
| trend | 趋势分析师 |
| industry | 行业从业者 |
| builder | 创业实践者 |
| technology | 技术与实现顾问 |
| need | 真实需求者 |
| bystander | 普通路人 |
| researcher | 用户研究员 |
| creative | 跨界创意者 |
| skeptic | 怀疑者／风险评审 |

用户批准的协议：

1. 开题 → 独立观点 → 动态交锋 → 状态整理 → 继续交锋。
2. 不限制为 15 轮，不设固定总轮数，直到用户点击“结束并总结”；批次大小是内部调度限制。
3. 同一角色可多次发言、支持、反驳、追问和补充，不强制每人每轮一句。
4. 允许被说服后修正观点，记录立场变化及理由。
5. 新观点减少、重复增加、冷场、重要共识或充分交锋的分歧触发主持人介入；不机械按时间/轮数总结。
6. 插话保存为用户事件，影响后续生成上下文，不能改写已有发言。
7. **当前默认手动逐条展示**；结束后弹出总结页，包含共识、未解决分歧、风险、假设、目标用户和验证行动。

协议详细设计：`docs/superpowers/specs/2026-10-11-hybrid-nine-person-discussion-design.md`；对应实施计划在 `docs/superpowers/plans`。

## 5. 新闻与社会热点

新闻素材和真实模型是独立能力：新闻来自外部网页/RSS，角色观点来自离线模板或已配置模型。两者均不能自动标成已核验事实。

- 大厅支持本次讨论获取相关新闻；社会热点雷达是独立页面，包含相关主题与一般热点。
- 用户要求优先接国内来源，国际消息走国内已有通道。
- 国内与国际尽量平均展示，可按地区与类别筛选；实际来源数量不平衡时不能伪造条目凑数。
- 刷新失败时保留上次结果并显示时间，缓存与新结果必须区分。
- `hotspots.py` 有后台并行抓取、刷新期限和独立缓存；外部来源可用性随网络变化。
- 当前 `config.py` 默认 RSS 包含中新网分类源以及 Google 新闻主题检索地址。**因此“所有请求均走国内”尚不能仅凭历史沟通或说明文档宣称满足，应检查实际 feed 配置与可达性。**
- 2026-10-12 已核对 `brainstorm/config.py` 实际默认源：`DEFAULT_RSS_FEEDS` = 1 条 `https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans` + 6 条 `www.chinanews.com.cn/rss/…`（scroll-news、china、world、finance、it、society）。**“国际消息走国内已有通道”并未被代码支持**：`hl/gl/ceid` 只是语言与地区参数，请求主机仍是 `news.google.com`。可达性未实测。
- README 中 BBC/Guardian 等新闻来源说明存在旧版本文字，不能据此断定当前线上请求源。

## 6. AI 接入与本机配置

支持 Anthropic 和 OpenAI 兼容接口；OpenAI 兼容实现用标准 HTTP `/chat/completions`，不依赖服务商专用 SDK。

本机已配置：

- provider：`openai`，运行时提供方标识为 `openai-compatible`。
- base URL：`https://api.deepseek.com/v1`。
- 请求模型：`deepseek-chat`。
- 用户明确授权启用 AI；密钥通过 Windows 当前用户 DPAPI 加密保存。
- 配置位置：`%LOCALAPPDATA%\九人圆桌\ai-settings.json`，不在项目/桌面程序目录内。
- 真实最小请求测试成功，回复 `OK`；服务响应模型字段为 `deepseek-flash`。不要把请求别名与响应模型标识混为一谈。

大厅“AI 设置”可修改服务地址、模型和密钥。保存不等于连通，下一次讨论应用设置。`mode=offline` 仍是硬离线边界；`auto`/`llm` 需同时允许联网和模型使用。

失败、取消、格式异常均需诚实说明和安全处理/回退；不要展示密钥、请求头或敏感异常。分享包不带本机设置，接收者需填写自己的服务密钥。

## 7. 最近一次缺陷与修复（不得回归）

用户反馈：发言气泡出现内部 JSON，且未看完就自动换下一条。

已查明根因：

- `RoundtablePage._generation_partial` 将模型原始生成文本直接写入气泡，虽然最终发言会通过 `_parse` 解析。
- `SessionController.manual_advance` 原来默认 `False`，`_emit_current` 会启动下一条定时器。

当前修复：

- `manual_advance = True` 为默认值，不启动自动切换计时。
- `_generation_partial` 只更新生成状态标签，不把原始文本放入气泡，也不覆盖正在阅读的观点。
- 正式发言依旧经结构解析后展示；生成失败保持诚实回退。
- 用户点击下一步推进一条；首条准备完毕会显示。后台首批准备不等同于自动播放。

新增回归测试：`test_default_discussion_waits_for_click_without_timer`、`test_generation_progress_never_displays_raw_model_payload`、`test_manual_generation_keeps_current_argument_visible`。三项测试先失败再通过。

## 8. 代码导航

| 文件 | 职责 |
| --- | --- |
| app.py | 桌面入口 |
| brainstorm/qt_app.py | 大厅、圆桌、总结、导航与生成状态显示 |
| brainstorm/roundtable.py、qt_theme.py | 自绘圆桌、视觉主题 |
| brainstorm/session_controller.py | 后台线程、取消、续批、播放、插话与结束 |
| brainstorm/playback.py | 不依赖 Qt 的播放状态机 |
| brainstorm/roles.py、models.py | 固定角色与讨论数据模型 |
| brainstorm/engine.py | 离线讨论、状态分析与整理 |
| brainstorm/turn_planner.py | 本地结构调度：谁被反驳未回、哪个提问没人答、谁久未发言、是否该主持人介入。**只做结构判断，不做语义相关性判断**；输出供模型编排层使用，也是模型不可用时的兜底 |
| brainstorm/llm.py | 模型请求、上下文、JSON 解析、usage、重试 |
| brainstorm/providers.py、config.py | provider 选择和网络/模型权限配置 |
| brainstorm/ai_settings.py | AI 设置对话框、地址校验与 DPAPI 存储 |
| brainstorm/news.py、hotspots.py、hotspot_page.py | 相关新闻、热点抓取/缓存与页面 |
| brainstorm/storage.py、export.py | 本地记录、版本兼容、JSON/Markdown 导出 |
| assets/avatars | 内置原创头像 |
| 九人圆桌-Qt.spec | 当前 Qt 打包配置 |
| desktop-release/verify-packaged-app.py | 验证真实可见 Qt 窗口，异常弹窗判失败 |

讨论历史默认在 `C:\Users\14726\九人圆桌`，当前存储 schema 版本为 6。历史查看不能自行联网或重新生成。

## 9. 运行、测试与打包

本机可用 Python：`C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`。

Qt/PyInstaller 依赖在项目 `.qt-build-runtime`，运行前将该目录放入 `PYTHONPATH`。旧命令中的 `.d-runtime` 当前不存在，不能照抄。

```powershell
$env:PYTHONPATH=(Resolve-Path '.qt-build-runtime').Path
$env:QT_QPA_PLATFORM='offscreen'
$py='C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m unittest discover -s tests -v
```

DPAPI 在受限沙盒中曾访问失败，正常 Windows 用户环境全量测试通过。不要为通过沙盒测试加入明文密钥回退。

2026-10-12 实测补充：**在 DSH 文件沙盒内直接跑上面的命令会“卡住”而不是失败**，表现为 `unittest` 停在某个用例上、进程持续吃 CPU 数分钟。根因已定位（非程序缺陷）：`tempfile.TemporaryDirectory()` 新建目录的 DACL 让沙盒进程自己都无法写入，`os.open(..., O_CREAT|O_EXCL)` 抛 `PermissionError`，而 CPython 的 `tempfile._mkstemp_inner` 在 Windows 上把它误判为重名并 `continue` 重试约 10000 次，于是空转；`TemporaryDirectory.cleanup()` 的 `os.scandir`/`os.chmod` 同样被拒，所以 `tearDown` 还会额外报 ERROR。`hotspots.py`、`storage.py` 等所有走 `tempfile` 的用例都会中招。

沙盒内改用：

```powershell
$env:PYTHONPATH=(Resolve-Path '.').Path + ';' + (Resolve-Path '.qt-build-runtime').Path
$env:QT_QPA_PLATFORM='offscreen'
& $py tools/run_tests_sandboxed.py
```

`tools/run_tests_sandboxed.py` 只是把 `TemporaryDirectory` 换成继承父目录 ACL 的普通目录，不改动被测代码。实测**127 项通过、0 错误 0 失败**，与正常环境结论一致。沙盒内创建的这种临时目录连 `icacls`/`takeown` 都删不掉，清理需要更宽权限。切到 `danger-full-access` 后限制消失，上面那条普通命令可直接通过（exit 0）。

```powershell
$env:PYTHONPATH=(Resolve-Path '.qt-build-runtime').Path
$py='C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m PyInstaller --noconfirm --clean --distpath dist-manual --workpath build-manual '九人圆桌-Qt.spec'
```

使用 spec 时不要追加 `--windowed`，当前 PyInstaller 会拒绝该选项；窗口模式已在 spec 内定义。不要使用旧 Tkinter spec。

旧包曾混入 Poppler 不兼容 ICU DLL，Qt spec 已限制 DLL 搜索路径；不要移除该修复。检查启动必须验证可见 Qt 主窗口，不能只看进程存在。分享整个程序文件夹，保留 `_internal` 与头像资源。

## 10. 已验证证据与边界

上一次交付会话的验证结果（2026-10-12 之前）：

- 127 项测试通过（此前版本为 124 项）。
- 最新 `dist-manual` 构建成功。
- 更新后的桌面 `九人圆桌.exe` 成功打开可见的 1920×1080 Qt 主窗口。
- 分享 ZIP CRC 检查通过，文件与桌面版内容校验一致，不包含 `ai-settings` 本机设置。
- DeepSeek 最小真实请求连通测试已成功；该测试发生在手动播放修复之前。

限制：未在最近修复后跑完整真实 DeepSeek 长讨论到总结导出；三项针对性回归通过不能代替用户对整场交互的满意度验收。未证明所有新闻源当前可达，未证明国际消息请求全经国内渠道。

2026-10-12 对话模型改造（第一期、第二期）的验证结果：

- **152 项测试通过、0 错误 0 失败**（基线 127 项，新增 25 项）。
- 上一轮修复的三项回归保护保持通过：手动逐条展示、气泡不显示原始模型载体、生成期间保持当前观点。
- 主窗口冒烟检查通过：`MainWindow()` 可构建，`show()` 后 `isVisible()` 为 True，正常关闭。
- 测试未污染 `C:\Users\14726\九人圆桌` 真实历史目录（已核对，测试时段内该目录无任何改动）。
- 未被验证的部分见第 12 节。

README、旧阶段文档、旧 dist/build 与 `desktop-release/九人圆桌桌面版-无限讨论` 有历史内容，**不可视为当前交付版本**。不要按旧说明把较旧 EXE 覆盖桌面最新版。

本目录已于 2026-10-12 初始化为 Git 仓库。对话模型改造在分支 `conversation-model` 上进行，回退点是基线提交 `c75f8b5`。`.gitignore` 当时已补全：`build-*/`、`dist-*/`、`.qt-build-runtime/`（单目录 660 MB）、`.pefile-runtime/`、`.uv-cache/`、`artifacts/`（43 MB 验证截图）、`desktop-release/九人圆桌桌面版-无限讨论/`（115 MB 历史打包程序）以及根目录旧 `九人圆桌.exe` 均不入库，仓库实际只有约 1.6 MB。**注意 `*.spec` 仍被忽略，所以打包配置 `九人圆桌-Qt.spec` 不在版本控制内。** 本仓库的 git 身份、`core.quotepath=false`、`core.autocrlf=false` 都只写在仓库本地配置里，没有动全局配置。

## 11. 接手后的推荐顺序

1. 读本文件，确认最新用户需求；再读 `AGENT_HANDOFF.md` 的完整视觉要求及对应 spec。
2. 核对源码、实际桌面 EXE 和本机设置状态；读取设置时只输出非敏感字段，不打印整份配置。
3. 如继续改动，保留手动逐条展示和内容来源标识，针对问题先复现再修复。
4. 需要进一步验证时，优先真实讨论闭环、生成等待期间旧观点是否保持、下一步一次一条、结束总结与导出。
5. 若优化新闻，先审查国内通道要求与实际 feeds 的差距，再测延迟、失败缓存与取消。
6. 发布时正常关闭旧程序，确认目标绝对路径后更新；验证启动与包内容，避免把秘密或用户历史打包。

## 12. 对话模型改造现状（2026-10-12）

用户要求"完善对话模型"，明确**有效性优先、请求次数与成本不设限**。设计文档 `docs/superpowers/specs/2026-10-12-conversation-model-design.md`，实施计划 `docs/superpowers/plans/2026-10-12-conversation-model-plan.md`。

**已完成（第一期、第二期）：**

- 提示词开始索要 `intent`、`stance_change`，并把 `event_id` 交给模型，结构化标记不再空转。
- `replies_to` 现在能按 `event_id`、`speaker_id` 或**显示名**回指，且一律解析到**最新**一条（此前只认 id，并且取最早一条）。
- 两条 provider 路径统一剥离 markdown 代码围栏。
- 新增 `brainstorm/turn_planner.py`：`extend_batch` 不再按名册轮转，改由结构事实决定发言人与回应对象。
- 五个协议介入触发条件（分歧充分交锋、重要共识、重复增加、冷场、新观点减少）在模型路径上生效，并产出主持人整理计划。
- 控制器记录 `host_intervention_reason`；界面在**实时与历史两条渲染路径**上统一显示"回应 XXX"和介入原因（此前历史路径连 intent 都不显示）。

**尚未完成（第三期、第四期）：**

- 每次发言前的**模型编排调用**（判断关键问题、这条必须回答什么、附带刷新状态）与后台预取。
- 生成后的**质检调用**（查重复、查回避、查编造），不合格回炉重写。
- 三段式长讨论上下文（常驻段 + 状态段 + 最近 24 条）；目前仍是最近 12 条纯文本。
- JSON 格式错误的回灌重试；当前仍是解析失败即整批回退离线。
- `duplicate` 标记尚无代码写入（`turn_planner.detect_intervention` 已在消费它）。
- 结束总结多遍成稿。

**必须由用户验收、实施者不得代为宣称的：** 真实 DeepSeek 长讨论里"谁回应谁是否合理""讨论是否真的更有效"。单元测试只能证明调度规则与标记生效，证明不了手感。

没有本文件之外的自动继续任务；以用户下一条请求为准。不要声称所有设计目标已完美实现。
