# 九人圆桌 · Agent 项目记忆与交接

更新日期：2026-10-12（Asia/Shanghai）。本文件结合用户确认、源码检查与本次会话实际验证整理。**先读本文件，再读 `AGENT_HANDOFF.md` 和相关设计文档。**

## 1. 一分钟了解项目

这是中文 Windows 桌面头脑风暴软件：用户输入主题，九个固定社会/职业视角讨论，主持人负责开题和整理，用户手动结束后打开总结与机会档案。

2026-10-26 起有两个分区，大厅角色面板右上角切换，不新开窗口：**商业痛点**（原九个职业视角，产出机会档案）与**事件讨论**（八个八卦性格的人，产出吃瓜纪要）。两套席位互不相干，App 名仍是「九人圆桌」。

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

### 7.0 两个分区必须一眼看出是两张桌子（2026-10-26，UI 收尾）

用户反馈"名字改，这个设定好怪"，随后要求"再改下UI"。定稿：App 名仍叫「九人圆桌」；大厅里两套人（商业痛点九个职业头衔、事件讨论八个口语绰号+卦名），切换后必须能立刻看出换了桌。

已做的四处改动（均在 `brainstorm/qt_app.py`）：

- 分区切换从"角色面板右上角两个小按钮"改为标题下两个大按钮：「商业痛点 → 机会档案」「事件讨论 → 吃瓜纪要」，当前项金色高亮（`LobbyPage.mode_buttons`）。
- 事件席位卡显示卦名与两面的样子：卡上大字是名字「乾明」，副标题是「乾·天 · 定调子、拍板的人」；`toolTip` 是「乾明（乾·天）\n阳面：…\n阴面：…」（`role_tooltip`）。
- 转写正文里每条发言带面别标签：「乾明 · 阳面　事实（已经确认的）　回应 坤兰」；`_speaker_tag()` 只在 `utterance.face` 非空时追加。
- 桌面页左上角徽标「八卦桌 · 事件讨论」（金色小字 `self.section_label`），商业模式隐藏；`_session_ready`/`load_session` 按 `session.mode` 显示。

回归测试：`tests/test_qt_ui.py::QtUiTests.test_event_seat_shows_trigram_and_both_faces`、`test_event_roundtable_says_which_table_you_are_at`、`test_business_roundtable_hides_the_event_badge`（断言用 `isVisibleTo(page)`，整页未 show 时 `isVisible()` 恒为 False）。

注意：`RoundtablePage` 的圆桌席位由 `set_selected_roles()` 决定，`controller.load()` **不会**改它；从大厅进入真实流程时 `MainWindow._start` 先调 `set_selected_roles` 再 `controller.start`，所以正确。自己写预览脚本时若只调 `controller.load()`，画面会留九个商业席位——那是脚本问题，不是产品缺陷。

### 7.0.1 八个事件席位改名为「卦名当姓」（2026-10-27）

用户："现在来改改名字，八卦的名字太傻逼了"，从三个方案里选了 **A：卦名当姓**。旧名（天哥/地姐/雷子/风姐/水哥/火姐/山哥/泽妹）已全部替换，源码、测试、说明书里 **零残留**：

| 卦 | 新名 | 卦 | 新名 |
| --- | --- | --- | --- |
| 乾·天 | 乾明 | 坎·水 | 坎川 |
| 坤·地 | 坤兰 | 离·火 | 离霞 |
| 震·雷 | 震山 | 艮·山 | 艮石 |
| 巽·风 | 巽竹 | 兑·泽 | 兑溪 |

- 名字 = 卦名 + 一个字（明/兰/山/竹/川/霞/石/溪），八个互不相同，且一眼看出对应哪一卦；`role_id`（qian…dui）不变，存档与测试不受影响。
- 席位卡：大字是新名「乾明」，副标题仍是「乾·天 · 定调子、拍板的人」；`role_tooltip` 改为「乾明（乾·天）\n阳面：…\n阴面：…」，避免「乾·天 · 乾明」重复。
- 转写标签变成「乾明 · 阳面　…」；`tests/test_qt_ui.py:553/559` 已同步。
- 顺带修一处不一致：离线模式八人开场原来没有面别（转写里前八条无「阳面」标签），现在 `engine.py:159` 走 `_add_face(..., "yang")`，与真实模型「阳面开场」一致。证据 `artifacts/probe_names.txt`（主持人无面、八人全阳面、第二段起出现阴面）。
- 历史跑测 `artifacts/real-event-3` 里的旧名字**故意不改**：那是当时的原始记录，改了就是伪造证据。
- 验证：266 测试全绿；桌面两份已用 `tools/deploy.ps1 -SkipBuild` 同时刷新（exe 哈希 `37096C05D5ACBB0C`，说明书 17740 字节带 BOM，分享 zip 186 条目/45.2MB），打包版窗口能正常开（1536×864「九人圆桌」）。


### 7.1 阴阳面的翻面必须由程序决定（2026-10-26，事件分区）

用户要求事件分区的人有"阴阳两面"。第一版把翻面交给模型（提示词让模型填 `face`），真实跑测 19 条发言 **全是阳面**——模型从不主动要求翻面，于是"两面"只是设定里的装饰。

修复：`resolve_face`（`brainstorm/llm.py:85`）由程序拥有规则。座位首次开口阳面；此后每次回来，只要距自己上一条发言已过 `FACE_COOLDOWN = 3` 条，就翻到另一面；冷却期内保持原面。模型的 `face` 字段不再能冻结某一个面。`brainstorm/engine.py` 的 `_face_after`（第 17 行）离线模式本来就是同一套交替规则，两条路径现在一致。

提示词同步改成"这一条你在X面（阳面：…／阴面：…）"并给出该面的原文描述，让模型的语气和分配到的面对齐，且不解释"为什么变脸"。

同批修复：主持人不再带面（`llm.py` 解析处 `spec.speaker_id != "moderator"` 才给 face）；真实跑测第 13/20 条主持人曾被标成阴/阳面。

证据：`artifacts/real-event-3` 共 20 条发言—10 条阳面、7 条阴面、3 条主持人无面；天哥第 10 条由阳转阴、地姐第 11 条转阴、第 15 条转回阳。回归测试 `tests/test_event_section.py::FaceFlipTests` 三条（先红后绿）与 `test_offline_event_discussion_keeps_both_faces_in_play`。

（`real-event-3` 是 2026-10-26 的原始记录，里面仍是当时的旧名字「天哥/地姐」；2026-10-27 席位改名为乾明/坤兰/震山/巽竹/坎川/离霞/艮石/兑溪。翻面证据本身不受改名影响，不要为了统一名字去改历史跑测文件。）

### 7.2 发言气泡出现内部 JSON，且未看完就自动换下一条

已查明根因：

- `RoundtablePage._generation_partial` 将模型原始生成文本直接写入气泡，虽然最终发言会通过 `_parse` 解析。
- `SessionController.manual_advance` 原来默认 `False`，`_emit_current` 会启动下一条定时器。

当前修复：

- `manual_advance = True` 为默认值，不启动自动切换计时。
- `_generation_partial` 只更新生成状态标签，不把原始文本放入气泡，也不覆盖正在阅读的观点。
- 正式发言依旧经结构解析后展示；生成失败保持诚实回退。
- 用户点击下一步推进一条；首条准备完毕会显示。后台首批准备不等同于自动播放。

新增回归测试：`test_default_discussion_waits_for_click_without_timer`、`test_generation_progress_never_displays_raw_model_payload`、`test_manual_generation_keeps_current_argument_visible`。三项测试先失败再通过。

### 7.3 发言像"模板套模板"，不像一群人在讨论（2026-10-27，已修）

用户原话：「我发现这些人的说话还是像模板套模板，不像一群人在讨论问题」。

**先量化，再改。** 拿真实跑测 `artifacts/real-event-3/real-20261027-001850.json`（20 条）统计：字数 min=154 / 中位=222 / max=257，**20 条全部落在 150–257 字**；8 个开场里 6 个以「我先说…」开头；9 条以「最后…」收尾。内容没错，但**每条的骨架和长度完全一样**——这就是观感的来源。统计脚本 `artifacts/analyze_transcript.py`。

**改了三件事：**

1. **每人一套说话习惯**（`brainstorm/models.py` 的 `Role.voice` + `brainstorm/roles.py` 的 `SEAT_VOICES`）。和"职责"分开写：职责是说什么，voice 是怎么说（句子长短、口癖、是否打断）。`_seat()` 里按 role_id 取。测试保证 17 个席位都有 voice、互不重复、且不等于 duty。
2. **篇幅由程序按条分配**（`brainstorm/turn_planner.py` 的 `TurnPlan.length_hint` + `assign_length()` + `LENGTH_CYCLE = ("short","short","normal","short","normal","short")`）。主持人 `host`、总结 `long`、首次发言 `normal`、其余按轮次循环。措辞在 `brainstorm/voice.py` 的 `LENGTH_TARGETS`。
3. **反模板约束 + 一次重写**（`brainstorm/voice.py` 的 `ANTI_TEMPLATE_RULES` / `looks_templated()`；`brainstorm/llm.py` 的 `_generate_turn_result` 里 `complaint = looks_templated(...)`）。禁套话开场（我先说/说白了/实话实说…）、禁分点、禁复述、要求点名接话、要求只做一件事；命中套话开场且不是主持人时**重发一次**，第二次解析失败就保留第一次的答案（不因风格丢整条）。

**实测对比（真实模型，同一套八个席位）：**

| | 改前 real-event-3 | 改后 real-voice-2 |
| --- | --- | --- |
| 字数 | 154–257（全部） | 53–162 |
| 模板词「最后」 | 9 / 20 | 1 / 20 |
| 点名叫人 | 65% | 95% |
| 开场 | 6/8 是「我先说…」 | 八个人各不相同 |

商业痛点分区同样生效：`artifacts/real-voice-biz-1` 21 条，59–156 字，点名 71%，机会档案内容仍成立。

**没有回归的地方：** 业务模式提示词里被测试依赖的规则文字（intent / stance_change / 不得重复）全部保留，只把固定长度改成按条分配。测试 266 → 283（新增 `tests/test_voice.py` 15 项）。

**注意：** 质检回炉现在会真的触发（两次跑测共 6 次带具体批评的重写），这是好事，但也意味着**请求数和等待会长一点**——用户已明确"花钱不重要，讨论有效性重要"。

## 8. 代码导航

| 文件 | 职责 |
| --- | --- |
| app.py | 桌面入口 |
| brainstorm/qt_app.py | 大厅、圆桌、总结、导航与生成状态显示 |
| brainstorm/roundtable.py、qt_theme.py | 自绘圆桌、视觉主题 |
| brainstorm/session_controller.py | 后台线程、取消、续批、播放、插话与结束 |
| brainstorm/playback.py | 不依赖 Qt 的播放状态机 |
| brainstorm/roles.py、models.py | 两套席位与讨论数据模型：`DEFAULT_ROLES`（商业痛点九个职业视角，原样不动）、`EVENT_ROLES`（事件讨论八个八卦人设，`_seat()` 把卦名／阳面／阴面写进 prompt，并带"传统引申不是心理学"的免责句）；`ROLES_BY_MODE`、`SECTION_TEXT`、`mode_for_roles`、`default_roles_for`、`face_label` |
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

### 交付目录只允许一套（2026-10-27 定）

用户原话：「你创建一个文件夹他就叫九人圆桌，然后里面放我自己点开的版本，另一个子文件你把直接发给别人的放进去……可以放备份，但是往上留一份就够了」。

桌面固定为**一个**文件夹，结构不许再变：

```
C:\Users\14726\Desktop\九人圆桌\
├─ 九人圆桌.exe            ← 用户自己双击的
├─ _internal\
├─ 使用说明.txt
├─ 发给别人的\
│   └─ 九人圆桌-发给别人用.zip
└─ 备份\
    └─ 说明.txt            ← 只留一份上一版；更新时把旧版整个目录挪进来并删掉更早的
```

部署顺序：更新前先把 `九人圆桌.exe` + `_internal` 整体移到 `备份\`（先清空 `备份\`），再把新包放进上层；**不要**在桌面或项目里另建 `九人圆桌热点版`／`九人圆桌桌面版*`／带日期的目录。桌面不要再放 `.lnk`：快捷方式和文件夹同名，反而分不清，用户直接进文件夹双击 exe。

打包中间产物同样只留一套：`dist-qt`（当前）与 `build-qt`（打包过程），打完即删 `build-qt`。2026-10-27 清理了 28 个历史打包目录（`build-*` / `dist-*`）与 `desktop-release\九人圆桌桌面版-无限讨论`，回收 1.79 GB——不要再攒。`desktop-release\verification` 里的截图证据体积小，保留。

### 更新 = 跑一条命令，两处一起刷新（2026-10-27 用户要求）

用户原话：「以后更新同时更新这两处」。已做成脚本，不要再用手工 cp/zip：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/deploy.ps1
# 只换文件不重新打包：追加 -SkipBuild
```

`tools/deploy.ps1` 依次做：PyInstaller 打包（到 `dist-qt`，成功后删 `build-qt`）→ 生成 `使用说明.txt`（UTF-8+BOM）→ 旧版整体移入 `备份\`（**哈希相同则跳过**，`备份\` 只留一份）→ 换上新的自己用那份 → 用**干净暂存副本**重做 `发给别人的\九人圆桌-发给别人用.zip`（绝不把 `发给别人的\`、`备份\` 套进 zip）→ 三项校验：两处 exe 哈希一致、`_internal\Qt6Core.dll` 存在、zip 内 exe 哈希一致且无设置/缓存/备份条目、说明书带 BOM。

已实测：`-SkipBuild` 路径 exit 0（本轮）；备份分支用临时目标目录（`-TargetRoot`）造了一个假旧版跑通——旧 exe/_internal/说明书进入 `备份\`、`备份\说明.txt` 保留、新版就位、zip 186 条目。`-TargetRoot` 只用于测试部署流程。

打包版启动验证仍需手工：`cmd /c start "" "<exe>"` 后**另起一次调用**查 `MainWindowTitle`／`IsWindowVisible`／尺寸，别在同一次调用结束前 Stop-Process（会把被测进程一起收掉）。

**编辑 `tools/*.ps1` 后必须补回 UTF-8 BOM**：`edit` 工具会写掉 BOM，PS 5.1 随即按 ANSI 读取，中文字符串全变乱码并报 `Unexpected token`。补 BOM 的命令见 §9 开头几节的 `WriteAllText(... UTF8Encoding($true))` 写法。

## 10. 已验证证据与边界

上一次交付会话的验证结果（2026-10-12 之前）：

- 127 项测试通过（此前版本为 124 项）。
- 最新 `dist-manual` 构建成功。
- 更新后的桌面 `九人圆桌.exe` 成功打开可见的 1920×1080 Qt 主窗口。
- 分享 ZIP CRC 检查通过，文件与桌面版内容校验一致，不包含 `ai-settings` 本机设置。
- DeepSeek 最小真实请求连通测试已成功；该测试发生在手动播放修复之前。

限制：未在最近修复后跑完整真实 DeepSeek 长讨论到总结导出；三项针对性回归通过不能代替用户对整场交互的满意度验收。未证明所有新闻源当前可达，未证明国际消息请求全经国内渠道。

2026-10-12 对话模型改造（第一期、第二期）的验证结果：

- **216 项测试通过、0 错误 0 失败**（基线 127 项，新增 89 项）。第一、二期 152 项；第三期前三项 162 项；热点混合与精简 189 项；修复两人锁死 191 项；边生成边显示 196 项；并发化独立观点 198 项；编排与质检 216 项。
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

用户要求"完善对话模型"，明确**有效性优先、请求次数与成本不设限**。设计文档 `docs/superpowers/specs/2026-10-12-conversation-model-design.md`；实施计划分两份：第一、二期 `docs/superpowers/plans/2026-10-12-conversation-model-plan.md`，第三、四期 `docs/superpowers/plans/2026-10-12-conversation-model-plan-2.md`。

**已完成（第一期、第二期）：**

- 提示词开始索要 `intent`、`stance_change`，并把 `event_id` 交给模型，结构化标记不再空转。
- `replies_to` 现在能按 `event_id`、`speaker_id` 或**显示名**回指，且一律解析到**最新**一条（此前只认 id，并且取最早一条）。
- 两条 provider 路径统一剥离 markdown 代码围栏。
- 新增 `brainstorm/turn_planner.py`：`extend_batch` 不再按名册轮转，改由结构事实决定发言人与回应对象。
- 五个协议介入触发条件（分歧充分交锋、重要共识、重复增加、冷场、新观点减少）在模型路径上生效，并产出主持人整理计划。
- 控制器记录 `host_intervention_reason`；界面在**实时与历史两条渲染路径**上统一显示"回应 XXX"和介入原因（此前历史路径连 intent 都不显示）。

**第三、四期（进行中，计划见 `docs/superpowers/plans/2026-10-12-conversation-model-plan-2.md`）：**

已完成：

- `brainstorm/jsonutil.py`：抽出共享的 JSON 剥围栏与校验，`llm.py` 与后续的编排/质检共用。
- **JSON 格式错误会回灌错误重试一次**，不再"错一次就整批掉回离线模拟"——这是用户反馈过的"怎么突然变离线了"的主要来源。
- **`duplicate` 标记开始被写入**：`turn_planner.mark_duplicates` 在控制器落盘时调用，按去空白后完全匹配判定，**只标记不删除**（协议 §3.1）。这让"重复观点增加"这个介入触发条件在真实使用中不再为空。

尚未完成：

- 每次发言前的**模型编排调用**（判断关键问题、这条必须回答什么、附带刷新状态）。提示词与解析已在计划中设计好，尚未写码。
- 生成后的**质检调用**（查重复、查回避、查编造）与不合格回炉。
- 三段式长讨论上下文（常驻开题与插话 + 状态段 + 最近 24 条）；目前仍是最近 12 条纯文本，长讨论会丢掉开题。
- 结束总结多遍成稿。

**2026-10-12 下午追加完成（第一轮真实跑测暴露问题后修的）：**

- **修掉两个必炸的崩溃**（都是先前就存在的 bug，一直没被真实讨论触发）：
  `llm.py` 里 `history + (utterance,)` 把列表与元组相加，抛 `TypeError` —— 这正是用户截图里「讨论生成失败；请稍后重试」的来源，只在最后一条主持人总结发言时发生；
  以及机会档案字段稍有缺失就抛 `ProviderFailure` 让整场失败。现在卡片有问题只降级卡片，绝不毁掉整场讨论。
- **发言精简**：提示词要求 200–350 字，`max_tokens` 从 1400 降到 800（`complete()` 另有 2600 的上限给长输出用）。实测角色发言从 500–900 字降到平均 292 字。
- **社会热点雷达改为混合来源**（用户要求）：真实新闻源优先（带真实来源与发布时间），AI 回忆作为补充并逐条标注模型自述的时间与来源。新增 `brainstorm/model_hotspots.py`，界面按「真实新闻源 / AI 回忆」分开标注。
- **`desktop-release/*.ps1` 补 UTF-8 BOM**：Windows PowerShell 5.1 会把无 BOM 的 UTF-8 脚本按 ANSI 读，脚本里的 `'九人圆桌'` 变成乱码，导致对正常程序误报"没有可见 Qt 主窗口"。

**2026-10-12 傍晚：两人对话锁死已修复。**

- 根因是 `turn_planner` 规则 3（被反驳且未回应者优先）：每次新的反驳都会产生一个新的"欠回应"，于是它一直压过公平轮换，A↔B 无限对轰。
- 修复：新增通用约束 `RECENT_WINDOW = 6` / `MAX_RECENT_TURNS = 2`——**最近 6 条角色发言里任何角色最多占 2 条**，两人交锋两轮后必须换人。规则 1（回应用户插话）标记为 `protect`，不受该约束影响。
- 真实复测（同议题、21 轮）：第 15–20 轮参与角色**从 2 个变成 4 个**；**9 个角色全部发过言**（此前 7 个从第 14 轮后完全沉默），最多者 3 条。
- 顺带收益：发言精简后整场从 131.8 秒降到 **69.5 秒**，token 从 106k/14k 降到 47k/5.5k。

**2026-10-12 傍晚（第二批）：首批等待已解决——改为边生成边显示。**

- 问题：`discuss()` 一次串行生成 14 条（开场 1 + 九个独立观点 + 三条交锋 + 总结 1），全部做完才交给界面，用户要盯 46 秒状态提示。
- 修复：`discuss()` 新增 `on_turn` 回调；`_GenerationWorker` 用 `turn_ready` 信号把每条已完成的发言立刻送到主线程；控制器用 `_live_session`（**主线程持有**，worker 不碰它）逐条追加，第一条到达时就开始播放并发出 `session_ready`，界面立刻进圆桌。
- **后台到货绝不自动翻页**：`_generation_turn` 只追加不推进，用户点「下一步」时才前进。首批仍在流式生成期间点击下一步，`next_step` 会拦住 `extend_discussion`，避免重复请求。
- 批次完成后 `_adopt_metadata` 把 provider 只在最后才填的字段（机会档案、usage、model_name、sources）搬到 live session 上，再以 `already_started=True` 调用 `_generation_state`，因此不会把用户位置重置回第一条。
- 真实测量：**第一条可见从 46.4 秒降到 2.9 秒**；后续每条约 3 秒到达一条（2.9/5.6/8.8/12.0/…/46.4）。
- 新增 `generation_progress` 信号，界面显示"正在后台准备后续发言…（N/14 条已就绪）"。
- 新增详细说明书：`docs/使用说明-详细版.md`（仓库内），程序文件夹里的 `使用说明.txt` 是同一内容的纯文本版。

**2026-10-12 晚：第三期核心（编排层 + 质检层）已实现，第九个"独立观点"改为并发。**

- 新增 `brainstorm/orchestration.py`：编排与质检的提示词构造和**防御性解析**（任何解析失败抛 `ValueError`，让调用方退回，而不是丢掉这一条）。
- `extend_batch` 现在是：本地结构计划 → **编排调用**（模型读完整事件流，决定关键问题、下一位发言人、这条必须回答什么、必须避免重复什么，**并顺手刷新状态**）→ 生成 → **质检**（查重复／查回避／查编造）→ 不合格则带着**具体批评**回炉一次。
- 降级路径都通：编排失败退回本地计划；质检失败视为通过并保留该条；回炉再失败也保留原条。**都不会中断讨论**。
- 状态刷新并进编排调用，**不额外占请求**。worker 只设置 `provider.last_state_refresh`，由主线程在 `_apply_batch` 里应用到 session（worker 不碰共享 session）。
- **代价：每次点击的请求数从 1 变成 3～4 次，用时约 7～8 秒**（用户已明确同意用有效性换这个代价）。
- 真实跑测（21 轮）：6 次追加全部是 3 次请求、质检全通过；状态刷新真的在更新（共识 3→4、分歧 3→4、未解决 4）；**九个角色各 2 条，参与完全均衡**；每条都带明确的 `replies_to`。
- **同时做了并发化**：九个"独立观点"改为 4 并发生成，而且**互不可见**（此前是串行且后一条能看到前一条，既慢又不符合"独立观点"的定义）。`generate_turn` 拆出无共享状态的 `_generate_turn_result`，避免并发时 `last_usage` 丢更新。真实测量：九条从逐条约 26 秒变成 **10.4 秒一次性就绪**；首批全部就绪从 46.4 秒降到 **24.0 秒**；第一条仍 **2.9 秒**可见。
- 测试从 196 增至 **216** 项。

**关于质检的诚实说明：** 真实跑测里 6 条全部通过，所以**"不合格 → 回炉重写"这条路只在单元测试里验证过，没有在真实模型上触发过**。不要声称它一定能提升质量。

**2026-10-12 晚（第三批）：热点可一键开讨论。**

- 用户要求："社会热点，我想点击他就直接以这个进行讨论。"
- 实现：`HotspotCard` 新增「就这个话题讨论」按钮，并且**点卡片空白处也可触发**（子控件按钮自己消费点击，所以"打开原文"和"完整摘要"不会被误触发）。信号链：card → `HotspotSection` → `HotspotPage.discuss_requested(topic, note)` → `MainWindow._discuss_hotspot` → 复用 `_start`。
- **来源与时间跟着材料走（关键）**：AI 回忆的条目带上"模型自述时间／来源、未核验、可能已过时"，真实新闻的条目带上媒体与发布时间；作为 `source_note` 进入 `TrendSource(source_type="user")`，最终出现在提示词的来源段。否则角色会把两年前的旧回忆当成今天的新闻来讨论。
- 角色取自大厅当前勾选；**一个都没勾时回退到全部九个**，避免开一场空圆桌（否则 provider 会抛"至少选择一位参与者"）。
- 这一场不再额外抓新闻，素材就是这条热点本身。测试 216 → **221** 项。

**2026-10-12 深夜（第四批）：修掉"同一句话显示两次"，并把发言类型翻译成人话。**

用户反馈两张截图：(1) 同一段发言上面一个金边气泡、下面又整段重复一次，问"怎么两个对话框都来了"；(2) 气泡上写"主持人 · 假设 · 模型生成"，问"假设是啥玩意"。

- **重复显示的根因（不是本轮改造引入的，基线 `c75f8b5` 就已经这样）**：圆桌页底部那一行的 `QLabel` 叫 `subtitle`，`_show_current_text` 里被赋值为 `utterance.content` 全文，而上面 `bubble` 已经显示了同样的全文。底部那一行本来只是给"插话"输入框占位用的。
- 修法：`subtitle` 改名为 `interjection_hint`，内容改成一行小字提示"插话会作为你的意见记录，并在下一批发言中得到回应"，**不再复制发言正文**；`_show_current_text` 只负责气泡。
- **「假设」= 发言类型（`ViewpointKind`）**，六取一：机会 / 风险 / 假设 / 待验证 / 总结 / 事实。它由**模型自己判断**，不是程序判定。
- 新增 `KIND_IN_PLAIN_WORDS`、`kind_label()`、`kind_legend()`：气泡上显示成「假设（还没证据的推测）」「风险（担心会出问题的地方）」等，鼠标停在气泡上或"完整讨论记录"标题上能看到六类对照表，表头写明"由模型自己判断，可能不准"。
- 气泡改写统一走 `_set_bubble(text, tooltip="")`：**状态文字不得继承上一条发言的类型图例**（"圆桌成员正在准备观点……"不该挂着"这一条是什么类型"）。
- **顺带修掉一个真 bug**：`_parse` 里模型返回一个我们不认识的类型词时，会**丢弃本地计划给出的类型、硬改成"假设"**。所以主持人的收尾总结被贴成了"假设"——这正是用户看到 `主持人 · 假设` 的来源。新增 `_viewpoint_kind(value, hint)`：先认模型给的，认不出就退回**本地计划已经知道的类型**，再认不出才用"假设"。先写测试确认失败（`AssertionError: ASSUMPTION != SUMMARY`），再改实现。
- 测试 221 → **226** 项；`tools/verify_ui.py` 之外的临时截图脚本只放在系统临时目录，未入库。

**2026-10-13 凌晨（第五批）：修掉五个逻辑缺陷，并让"质检回炉"看得见。**

用户问"你觉得还有什么逻辑上可以优化的东西"。五个缺陷都用真实代码复现过，不是推测；每个都先跑出失败证据再改。计划与证据见 `docs/superpowers/plans/2026-10-13-conversation-logic-plan.md`。

- **主持人会霸占圆桌（最严重）**：`detect_intervention` 只看角色发言，主持人自己的收束**不改变任何触发条件**，所以触发一旦成立就永远成立。实测连续三次 `plan_turn` 都返回 moderator。修法：`MODERATOR_COOLDOWN_TURNS = 4` + `moderator_available()`；`plan_turn` 的介入分支加门控；`parse_orchestration` 在冷却期内拒绝模型的 moderator 请求（抛错让调用方退回本地角色计划）。**`detect_intervention` 刻意保持"只报证据"**，因为控制器要用它填 UI 的"介入原因"，这样 5 个触发条件测试与介入原因测试都不用改。顺带修掉优先级矛盾：现在「优先回应用户插话」恢复最高优先级。
- **模型选的发言人绕开公平性上限**：`parse_orchestration` 直接换人、从不调 `_guard`，所以"连续不超过 2 条 / 最近 6 条最多 2 条"只保护兜底路径。实测让编排器每次选 `trend` → `['trend'] * 6`。修法：新增公开包装 `enforce_fairness()`，`extend_batch` 在编排成功后调用；提示词里增加第 6 条硬规则与「发言权分配事实」，先让模型自己守规矩。修复后同场景得到 `['industry','technology','need','trend','bystander','trend']`。
- **主持人→角色改写后阶段标签错乱**：`replace()` 保留了主持人计划的 `phase=状态整理 / kind=总结 / intent=synthesize`。修法：本地计划本来是主持人时，把三者重置为 `动态交锋 / 假设 / elaborate`。
- **用户插话永久留在提示词里**：`rebuild_state()` 从不清除 `pending_user_interjection`，而调度器 6 条后就过期。实测第 12 条时调度器已不再优先、提示词却仍带着原话。修法：`models.USER_INTERJECTION_WINDOW = 6` + `DiscussionSession.pending_interjection(window)`，**调度器与状态派生共用同一个谓词**。常量放 `models.py` 以避免 `turn_planner → models` 的反向导入。
- **被指派回应谁，却看不见原文**：生成提示词只渲染最近 12 条，而被指派对象从完整历史里找、只打印编号和名字。实测 21 条历史时 `target event id present? True / target CONTENT present? False`。修法：指令行带原文引用（截断 240 字）；新增 `_render_opening_positions()`——每角色一条"最初立场"（截断 120 字，最多 9 条），仅在滑出最近窗口时加入，并按 `event_id` 与最近窗口及被引用那条去重。**不增加任何模型请求**，这是"三段式长讨论上下文"的最省做法。去重是写测试时发现的：被引用的那条会同时出现在指令和首轮段里。
- **编排缺 `must_answer` 丢掉整次编排**：空白值现在记为空串（生成提示词本来有 `plan.must_answer or plan.reason` 兜底），模型选的发言人与同一次请求里的状态刷新都保住了。这是**有意的契约变化**，对应测试已改名。
- **主持人收束跳过质检 + 回炉不可见**：去掉 `if plan.moderator: return` 提前返回；`Utterance` 新增 `review_note`，回炉成功时写入批评，`storage.py` 往返它但**不加 schema 版本**（保持 v6，旧文件缺键即空串）；`_transcript_line` 在「完整记录」里显示 ` · 质检重写：<批评>`。修复前证据用 `git show HEAD:...` 取：llm.py 里有那句提前返回、models.py 里没有 `review_note`。
- 顺手修了**验证工具的失真**：`tools/run_real_discussion.py` 从不应用 `provider.last_state_refresh`，所以导出的共识/分歧看起来永远是空的。现在它照 `_apply_batch` 的做法应用，并打印 `review_note`。
- 测试 226 → **248** 项。

**第五批真实模型跑测（2026-10-13 01:02 / 01:04，deepseek-chat，40 次与 33 次请求）：**

- **主持人没有霸占圆桌**：8 次延展与 6 次延展里**主持人 0 次**（全程只有首批的开场＋阶段总结和结束时的那条总结）。
- **发言权均衡**：23 条里 9 个角色各 2～3 条；21 条里各 1～3 条。没有任何角色连续 3 次。
- **状态刷新真的在工作**：共识 3 条、分歧 2 条、未解决 4 条，内容具体（例如"持续陪跑工时缺乏经费科目，中介断供风险可能高于技术风险"）。
- **每题 5.8～10.3 秒**，首批 14 条约 22 秒，总用时 66～89 秒。
- **`review_note` 全程为空**：又跑了 14 次延展，**质检依然一次都没打回**。所以"回炉能提升质量"仍然未被真实模型验证——现在至少能在记录里看见它有没有发生。**下一步值得查的是：质检者是不是个橡皮图章**（它从未在真实模型上判过不合格，唯一会失败的证据来自固定回复的单元测试）。

**仍然存在的限制：**

1. **首批 14 条在后台生成，全部就绪约 24 秒**（九个独立观点已并发）。用户 2.9 秒就能开始读，等待感已消除。
2. **模型没有实时新闻能力**：实测两次抓取 20 条全是 2024 年前后的事，两次重合 0/10。「AI 查当下热点」在当前模型上做不到，只能逐条标注模型自述的时间与来源。这条不是 bug，是模型能力边界。
3. **每点一次「下一步」约 7～8 秒**（3～4 次请求）。这是编排与质检的代价。
4. **质检回炉路径未经真实验证**（见上）。第五批之后它不是"看不见"，而是"从没发生"——这本身就是个待查的问题。
5. 第三期剩余项：三段式长讨论上下文的**后半段**（现在有"最近 12 条全文 + 各角色首轮立场"，还没有跨多轮的滚动要点）、结束总结多遍成稿、后台预取。这些都不影响"每条发言是否推进关键问题"。

**桌面上多了一个工具：** `tools/make_share_zip.ps1` 用来生成可直接发送的分享包。它先建到临时文件、验证条目数/分隔符/CRC/敏感文件，全部通过才发布——因为曾出现过"手工建 zip 失败产生 0 字节坏包并覆盖好包"的事故。注意本机 PowerShell 执行策略禁止直接运行 .ps1，要加 `-ExecutionPolicy Bypass`。

**坑：改完 `九人圆桌热点版\使用说明.txt` 之后必须补回 UTF-8 BOM。** 这个文件是要发给别人的，早前专门加过 BOM；用编辑工具改它会把 BOM 吃掉（第五批就发生过，已补回并重建 zip）。检查与修复：

```powershell
$p = "$env:USERPROFILE\Desktop\九人圆桌热点版\使用说明.txt"
$b = [System.IO.File]::ReadAllBytes($p)
if (-not ($b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF)) {
    $t = [System.IO.File]::ReadAllText($p, [System.Text.Encoding]::UTF8)
    [System.IO.File]::WriteAllText($p, $t, (New-Object System.Text.UTF8Encoding($true)))
}
```

改完记得重建分享包，否则 zip 里还是旧的说明文件。程序**代码**文件（`brainstorm/*.py`）用普通 UTF-8 即可，不需要 BOM；`运行开发版.bat` 例外，它必须是 **GBK + CRLF**。

**明确延后：后台预取。** 它只影响等待时间、不影响讨论有效性，却要改动线程模型与并发约束，风险收益比不合适。注意第三、四期做完后，**每次点击会发 3～4 次模型请求**（编排 → 生成 → 质检，不合格再加一次回炉），这是用有效性换来的已知代价，等待会明显变长。

**必须由用户验收、实施者不得代为宣称的：** 真实 DeepSeek 长讨论里"谁回应谁是否合理""讨论是否真的更有效"。单元测试只能证明调度规则与标记生效，证明不了手感。

## 14. 情绪账本与分层议题（2026-10-27 下午）

用户的判断：按轮次翻面是程序化的假反应，讨论 20 轮就到底、并且九个人像在套模板。

**情绪账本替换了"按轮次翻面"。** `brainstorm/mood.py`：`mood_of(history, seat)` 从历史重算心情（-2…+2），`validate_notes` 校验模型交上来的 `reactions`（`Reaction(seat_id, delta, why)`，每条发言最多惹到两个人，不能戳自己），`resolve_face` 只由账本决定脸——模型不再自己声明"我现在是阴面"。`CHANGE_COOLDOWN = 3` 是同一个人两次变脸之间至少隔三条；`FADE_EVERY = 4` 是隔四条气开始消。存储 schema 仍是 6，`reactions` 单独序列化。

**分层议题解决"太长/太短"两头的问题。** `brainstorm/agenda.py`：商业五层（现象/原因/谁受益谁付代价/现有做法为什么不够/可下手的切口），事件五层（发生了什么/谁受损谁得利/各方说法与动机/处理方式与代价/怎么收场），`LAYER_TURNS = 6`，主持人和用户插话不推进层数。提示词里带上"这一层在聊什么、这一层第几条、没聊透别换层"；主持人只有在最后一层才允许整场总结。

**踩到的真 bug：** `llm._parse` 引用了不存在的 `roles`（`seat_ids={item.id for item in roles}`），mood 那次提交后事件模式每条发言都会 NameError。真实模型跑测在提交之前，所以没暴露。已改成"历史里说过话的席位"。

**测试：** 312 项（mood 19 + agenda 8）。部署与 zip 需重做后再交付。

## 15. 脸色上桌、议题往下走（2026-10-27 晚，第二轮）

**分层议题扩到八层并取消上限。** 事件桌八层（发生了什么／谁受损谁得利／各方说法与动机／处理方式与代价／怎么收场／同类事以前怎么处理／谁该先动怎么动／还差什么才能下结论），商业桌五层。`LAYER_TURNS = 6`，八层走完回到第 1 层，但带着"这些已经说过了"的清单。主持人整场收束只在第 4 层之后可用。

**脸色画到了桌面上。** `RoundtableCanvas.set_mood/set_quiet`：每个座位下面三颗点（红=挂脸、暗金=正常、金=心情好）；`quiet_seats(utterances, seats, lookback=5)` 判断"最近 5 条既没说话也没人提他"，座下写「一直没人接他」。`RoundtablePage._sync_table_mood()` 在每条发言后与加载历史后同步；商业桌不开这套（`session.mode != "event"` 直接返回）。

**质检收窄，重写率从 5/8 降到 1/8。** 两个真问题：①`review.passed` 被 `avoided`（没答全）拖成 False，其实 `parse_review` 早已单列；真正卡人的是 `repeats` 与 `fabricated`。②`fabricated` 的定义太宽，把"我听说有人去问过物业"也判成编造。现在的规则写在提示词里：只有把**具体数字、日期、文件名称、机构或专家原话**当成真的说、或冒充自己亲自核实过，才算编造；「我听说」「我猜」这类转话不算。

**`_ensure_reaction` 放宽。** 模型没写 `replies_to` 时，就当他在反驳上一个说话的人（跳过主持人与自己），记一笔 −1——否则账本常年空白、永远不翻脸。

**实测（真实模型，事件桌，22 条）：** 8 笔情绪记录、3 条阴面、1 次质检重写、39 次请求、67.1s。改前同题：0 笔、0 条阴面、5 次重写、45 次请求、79.3s。

**测试 324 项。** `tests/test_mood.py` 加了 4 个 `quiet_seats` 用例，`tests/test_qt_ui.py` 加了「事件桌有三颗点且能画出被晾着的座位」「商业桌不显示脸色」两个用例。追加测试时注意：`tests/test_qt_ui.py` 末尾有 `if __name__ == "__main__": unittest.main()`，往里追加会被塞到那个 if 里面（AttributeError: type object has no attribute ...）；要插在 guard 之前。

## 16. 第三个分区「观点讨论」（2026-10-27 晚，第三轮）

**为什么加。** 用户原话：「我让重新加的另一个对某观点或者某说法的讨论去哪了，单开一个板块好吗宝贝」。商业痛点问"值不值得做"，事件讨论问"这事儿怎么回事"，两者都不适合"这句话到底站不站得住"。所以单开第三桌。

**模式 id `"claim"`，产出「说法体检单」。** 六个档案字段按同一套 `OpportunityCard` 装，只是名字换掉：这说法在说什么／谁在这么说／站得住的理由／反例与边界／还缺什么证据／怎么用、怎么验。三套文案都在 `brainstorm/roles.py` 的 `SECTION_TEXT`，`tests/test_claim_section.py` 断言三套 key 完全一致——改一处必须改三处，否则档案页会 KeyError。

**八个席位（`CLAIM_ROLES`）。** 主张者／挑刺者／数据员／行内人／条件派／动机派／类比手／外行。id 前缀 `claim_`。八个人各站这个说法的一个位置，没有"正反两面"这套东西（用户明确否掉了程序化翻面）。

**议题五层（`agenda.CLAIM_LAYERS`）。** 这说法到底在说什么／它凭什么站得住／什么情况下不成立／谁在这么说、图什么／能信到什么程度、怎么用。`LAYER_TURNS = 6`。

**事件桌从五层补到八层。** 之前 `PROJECT_MEMORY` 写了八层但代码只有五层（发现时正在核 20 轮上限），已补齐：同类事以前怎么处理／谁该先动、怎么动／还差什么才能下结论。现在事件桌理论上能聊到 48 条。

**「缺的是……谁统计的、哪一年」会被抄成模板。** 第一场真实跑测 19 条里"谁统计"出现 10 次、"缺的是"6 次。已在 claim 规则里加第 10 条：别每条都用同一句式补"缺的是"，缺证据只在真卡住时提且换问法。测试 337 项。

## 17. 往 GitHub 上传的坑（2026-10-27 晚）

**用户要求：每次更新都推到 GitHub；介绍和使用说明要中文。**

- 仓库：`https://github.com/YYQking/jiuren-yuanzhuo`（原名就是一个减号，2026-10-27 改成 jiuren-yuanzhuo），分支 `main`。
- 推送靠 HTTPS + Windows 凭据管理器里存的 PAT（用户名 `YYQking`）。全局曾经有一条把 github.com 改写成 `gh-proxy.com` 的 `insteadOf`，已删；本仓库 `http.proxy` 是空串（不是没设）。
- **`github.com:443` 会间歇性连不上**（`api.github.com`、`codeload.github.com`、`ssh.github.com:443`、`uploads.github.com` 都通）。连不上时 `git push` 报 `Failed to connect to github.com:443 after 21000 ms`，重试几次可能通。
- 兜底路线（已验证可用）：用 API 发文件（`PUT /repos/:o/:r/contents/:path`，带 `sha` 表示更新）和传发行包（`POST /repos/:o/:r/releases` + `POST uploads.github.com/.../assets?name=`）。脚本在 `artifacts/publish_docs.py`、`artifacts/upload_release.py`（token 从 `git credential fill` 读，不打印）。
- **GitHub 会把发行包附件的非 ASCII 文件名剥成 ASCII 残骸**：`九人圆桌-发给别人用.zip` 变成 `-.zip`，`九人圆桌.exe` 变成 `default.exe`。附件名只能用英文，已改成 `jiuren-yuanzhuo-2026-10-27.zip` / `jiuren-yuanzhuo.exe`，正文里用中文说清是什么。
- 约 300MB 的程序目录**不要塞进仓库**：会永久占 git 历史，每次 clone 都要下。发行包放 Releases 附件，仓库里只留 `发行包/说明.txt` 指路。
- 仓库里的 `README.md` 是给人看的总览，`更新记录.md` 是按日期的人话变更表；`docs/使用说明-详细版.md` 是详细手册，打包时由 `tools/build_manual_txt.py` 渲成包内 `使用说明.txt`（UTF-8 带 BOM + CRLF，别丢）。
- 提交信息从这一刻起用中文——用户看不懂英文提交。

没有本文件之外的自动继续任务；以用户下一条请求为准。不要声称所有设计目标已完美实现。
