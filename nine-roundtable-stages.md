# 九人圆桌项目阶段记忆

## 项目定位

“九人圆桌”是一个 Windows 桌面头脑风暴软件：九个不同社会视角围绕主题进行讨论，最后收敛为机会方向、风险、假设与验证行动。

当前技术栈为 Python + PySide6，界面是沉浸式深森林绿/炭黑/胡桃木/暗金的赌场牌室风格圆桌；讨论保留离线模板回退，并可在用户开始讨论时联网获取公开新闻素材。

## 已完成的 A 阶段基线

- Qt 主窗口与大厅、圆桌场景、历史记录和导出流程已存在。
- 九个稳定角色 ID、原创 SVG 头像、中央圆桌、角色席位、主持人中心位、逐条播放、暂停/继续/跳过、完整记录抽屉、用户插话入口均已具备。
- `MockDiscussionProvider` 生成明确标注为模拟观点的完整离线 session。
- 支持本地 SessionStore 保存、历史加载、JSON/Markdown 导出。
- 离线默认路径不依赖 API Key、SDK 或网络。

## B 阶段状态：已完成

### 已完成

- `AppConfig` 支持：
  - `BRAINSTORM_MODE=offline|auto|llm`
  - `BRAINSTORM_ALLOW_NETWORK`
  - `BRAINSTORM_RSS_FEEDS`
  - 超时、RSS 最大条目、LLM 重试次数
  - LLM 模型名与 API Key 读取；API Key 使用 `repr=False`
- RSS provider 支持注入 transport，默认不主动联网。
- RSS 结果带来源标题、链接、摘要、可信度、来源类型和时间字段。
- Qt RSS 抓取使用 `QThread`，不在抓取期间直接阻塞 UI。
- 大厅默认勾选 RSS 获取，用户可在开始前取消；强制 offline 模式不可联网。RSS 来源明确标记为“未核验”。
- Session 和导出包含 provider、网络使用、来源和生成状态等元数据。
- 旧 v2 session 基础字段默认兼容，schema 当前为 v4。
- RSS 先于讨论生成、使用后台线程抓取；原始 RSS 来源通过独立参数进入真实模型上下文，用户线索不再与 RSS 混为一谈。

### 收尾结果

- RSS 结果现在明确区分尝试、成功、命中、部分失败和完全失败；缺少文章链接时不会伪造 feed URL。
- Atom ISO-8601 时间、`rel=alternate` 链接、摘要匹配、时区、跨 feed 去重和边界测试均已覆盖。
- v2/v3 历史迁移补齐新闻元数据默认值，并拒绝未来 schema 版本。
- Qt RSS worker 支持重复启动清理和完成后引用释放；状态元数据进入 UI 与 Markdown 导出。
- README 保留 RSS 与真实模型显式 opt-in、未核验和离线回退约束。

## 联网与观点来源说明（2026-10-11）

- 默认 RSS 源包括 Google News 主题搜索以及 BBC / Guardian 的世界、商业、科技、科学与环境订阅；可由 `BRAINSTORM_RSS_FEEDS` 替换。主题搜索地址支持 `{query}` 占位符。
- RSS 仅是配置订阅源实际发布、且按关键词匹配的素材，不代表全网覆盖。按发布时间排序，日期缺失的条目排在最后；部分源失败时显示部分失败。
- 九个席位是职责不同的模拟角色，不是九位真实人士或九个独立 AI。默认模型关闭时使用程序内角色模板；RSS 作为单独的未核验新闻材料展示，模板模式不会伪装成已对新闻做语义推理。
- 启用真实模型并成功请求时，模型会依据角色职责、主题、用户线索、原始 RSS 元数据和前文生成观点；观点本身仍须核验。来源说明显示于记录面板、总结页和 Markdown 导出。
- `BRAINSTORM_MODE=offline` 继续作为不可绕过的离线硬边界。

## C 阶段状态：已完成

### 已完成的 C 基础安全接缝

- `resolve_providers()` 作为组合根，集中选择讨论和新闻 provider。
- `offline` 是硬边界：始终使用 Mock + OfflineNews，不因 feed 或 API Key 配置而联网。
- 真实模型选择要求同时满足：
  - mode 为 `auto` 或 `llm`
  - 允许网络
  - 显式允许真实模型
  - API Key 存在
  - 模型名有效
  - Anthropic SDK 已安装
- 缺少配置、SDK 或权限时安全回退到 Mock，并记录回退原因。
- provider 请求失败时 controller 会回退到 Mock，避免把失败伪装成真实模型结果。
- `schema_version` 已推进到 4。
- Anthropic adapter 的 `discuss()` 已开始支持 `on_partial` 与 `cancel_event` 参数，并在每个阶段转发 partial 内容、重置本次 usage。

### 收尾结果

1. **后台生成已移出 Qt UI 线程**
   - `SessionController` 使用 `_GenerationWorker` + `QThread` 调用 `provider.discuss()`。
   - worker 只负责 provider 调用；session、playback 和 UI 信号在 controller 线程处理。

2. **阶段化后台编排已由 provider 负责，controller 提供线程边界**
   - 目标顺序：主持人规划 → 角色独立观点 → 正反交锋/补充 → 主持人总结与机会档案。
   - 后续 turn 必须使用已完成 utterances、RSS 素材和用户插话上下文。
   - 需要 generation token 防止旧 worker 覆盖新 session。

3. **取消、状态和 partial UI 已接入**
   - controller 提供 generation 状态、取消事件和 partial 信号。
   - 新启动、加载历史、返回大厅和关闭窗口都会使旧 token 失效，旧 worker 结果不会覆盖当前会话。
   - 取消会显示“正在取消/已取消”，不会伪装成暂停。

4. **Anthropic adapter 已硬化**
   - fake streaming 覆盖了 usage、嵌套 message usage、空白内容、畸形 JSON/schema、取消和重试。
   - 真实模型输出继续标记为未核验的模拟观点，不升级为事实。
   - `replies_to` 保持 speaker-level 兼容语义。

5. **Provider resolver**
   - `llm_model` 缺失时应在回退原因中明确写出“未配置模型”。
   - SDK 可用只表示“可尝试”，不表示请求成功；UI/status 不得把配置成功写成生成完成。

## 关键文件

- `app.py`：应用入口
- `brainstorm/config.py`：环境配置
- `brainstorm/providers.py`：provider resolver 与 IntegrationStatus
- `brainstorm/news.py`：Offline/RSS provider
- `brainstorm/llm.py`：Anthropic 适配层、结构化解析、Usage、取消/partial seam
- `brainstorm/session_controller.py`：Qt session、新闻 worker、播放控制；C 阶段主要改造点
- `brainstorm/models.py`：session/source/utterance/opportunity 数据模型
- `brainstorm/storage.py`：本地保存与 schema
- `brainstorm/export.py`：JSON/Markdown 导出
- `brainstorm/qt_app.py`：大厅、圆桌页面和 Qt wiring
- `tests/test_engine.py`：离线引擎测试
- `tests/test_b_integration.py`：当前 B 集成测试
- `tests/test_persistence_playback.py`：持久化与播放测试

## 当前验证基线

- 现有非 Qt unittest：14/14 通过；新增 Qt 生成测试在缺少 PySide6 的环境中明确跳过。
- `python -m compileall -q brainstorm app.py tests` 通过。
- 未执行真实网络请求、真实 Anthropic 请求或完整 Qt offscreen smoke test；需要在带 PySide6 的运行环境补做。
- 并行实现代理此前多次因服务端 524 超时失败；不能把代理失败当作代码完成。

## 后续实施优先级

1. 先修正 RSS 失败/成功元数据语义和旧 schema v2/v3 测试。
2. 为 Anthropic adapter 增加 fake streaming client 测试并完善 `discuss` 的 partial/cancel/usage/retry。
3. 在带 PySide6 的环境运行 Qt offscreen smoke test，确认 worker、取消和线程清理。
4. 加强 Anthropic fake streaming、RSS 边界和 v2/v3 迁移测试。
5. 再考虑新的 one-folder 打包；不能覆盖既有 `dist-final`、`build-final` 或 `build-stage-b`。

## 安全与产品约束

- 离线仍是默认路径。
- 不因存在 API Key 自动联网。
- RSS 内容永远是未核验素材，不能升级为事实。
- 不保存 API Key，不把 key、请求头、原始异常或网络细节写入 session/export/UI。
- 真实模型失败时诚实回退，不能把 Mock 结果标记成 Anthropic。
- 不在未经确认时覆盖已有 EXE 或发布目录。

## D 阶段状态：已完成

### 已完成

- `cancel_generation()` 先使 generation token 失效，再通知 worker 取消；provider 即使忽略取消事件，迟到结果也不能覆盖新会话。
- 返回大厅、加载历史和关闭窗口沿用同一 token 失效语义；取消状态仍显示为“正在取消/生成已取消”。
- RSS worker 在完成后释放 worker/thread 引用，减少重复启动时的 stale 生命周期残留。
- 新增取消竞态和 RSS worker 清理回归测试；完整非 Qt 测试通过，Qt 测试在未安装 PySide6 的环境中明确跳过。
- 对已有 `dist-stage-b` Qt one-folder 包做了 offscreen 启动检查：进程可启动并持续运行，Qt 平台插件和 9 个头像资源均存在。
- 使用隔离的 PySide6 6.12.0 + PyInstaller 6.22.3 完成真实 Qt 生命周期测试：6/6 通过；完整项目回归 39/39 通过。
- 生成过 `dist-stage-d/九人圆桌-Qt/` one-folder 包；后续发现 offscreen 进程存活检查无法识别启动异常弹窗，该旧包的启动验收失效。

### 发布验证记录

- 源代码默认运行时仍不带 PySide6，但 D 阶段使用项目内隔离目录 `.d-runtime` 完成测试和打包，未修改系统 Python。
- 新包入口、Qt 平台插件、9 个头像资源均存在；未覆盖任何旧发布目录。

### D 阶段发布边界

- 不覆盖 `dist-final`、`build-final` 或 `build-stage-b`。
- one-file 不属于阶段目标；当前交付物为 one-folder 包。

## 桌面版 QtCore 启动故障修复（2026-10-10）

- 用户截图中的错误已复现：QtCore 导入失败，Windows 返回 DLL 错误 127。
- PE 导入检查确认旧包的 `icuuc.dll` 来自打包机 PATH 中的 Poppler，缺少 Qt 所需的 20 个无版本后缀入口；隔离 Qt 环境加载的是 Windows System32 的 ICU。
- Qt spec 将打包依赖搜索路径限制为 Qt、Python 和 Windows，避免混入同名的不兼容工具库。修复输出使用 `build-qt-repair/` 和 `dist-qt-repair/`，保留历史目录。
- 完整源代码回归 39/39 通过，无跳过。Windows 启动回归先确认旧包出现异常弹窗，再确认修复包和桌面安装包显示标题“九人圆桌”的可见 Qt6120QWindowIcon 主窗口，尺寸 1536×864；截图保存在 `desktop-release/verification/`。
- 桌面已更新 174 个文件，逐文件 SHA256 核对通过；真实启动桌面快捷方式后，可见 Qt 主窗口通过再次确认并继续运行，结果保存于 `desktop-release/verification/desktop-shortcut.json`。故障包保存在桌面 `九人圆桌桌面版-旧包-20261011-020716`。讨论数据仍保存在用户目录的“九人圆桌”。

## 无限讨论与 UI 优化（2026-10-11）

- 圆桌播放不再因为固定轮次自动结束；到达当前记录末尾时，用户点击“下一句”会追加一批离线模拟回应。
- 追加批次允许同一角色多次发言，并通过 `replies_to` 保留回应、补充和反驳关系；没有总批次上限。
- 用户点击“结束并总结”后才进入独立机会档案页，完整展示支持理由、风险、待验证假设、下一步和观点分布。
- 大厅角色区改为可滚动布局，圆桌记录抽屉增加滑出动画，并补充显式退出、窗口化和静音状态入口。

## 混合讨论模式实施（2026-10-11）

- 讨论进入“开题 → 首轮观点 → 动态交锋 → 状态整理”的无限循环，不按固定总轮数结束。
- 角色可以多次发言，结构化记录支持支持、反驳、追问、补充和主持人整理等意图，并保存回应事件。
- 状态快照跟踪共识、分歧、未回答问题、重复度、活跃分歧和每个角色的当前立场。
- 角色可记录立场变化的前后内容、触发理由和引用事件；用户插话会优先进入下一批回应上下文。
- 每批追加后保存会话，历史和导出包含事件元数据、讨论状态、立场轨迹和未核验来源标记。
- 圆桌 HUD 与总结页展示共识、未解决分歧、未回答问题和立场轨迹；离线模拟与真实模型来源继续明确区分。
