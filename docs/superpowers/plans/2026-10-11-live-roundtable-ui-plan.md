# 无限圆桌与沉浸式 UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将九人圆桌升级为可无限追加、手动结束并显示完整总结页的沉浸式桌面应用，同时修正大厅和圆桌布局适配。

**Architecture:** 保留现有 Qt/Python 业务模型，在 provider 层增加基于 session 的追加对话，在 controller/playback 层增加 live 生命周期，在 Qt 层拆出总结页并将大厅角色区改为可滚动布局。离线模拟始终显式标注，历史和导出继续复用现有模型。

**Tech Stack:** Python 3.12, PySide6, unittest, PyInstaller one-folder。

---

### Task 1: 追加对话的领域行为

**Files:**
- Modify: `brainstorm/engine.py`
- Modify: `brainstorm/models.py`
- Test: `tests/test_engine.py`

- [ ] 写失败测试：追加批次包含多次同一角色发言、`replies_to` 指向已有发言、不会引入未选角色，并更新机会档案统计。
- [ ] 运行 `python -m unittest tests.test_engine -v`，确认新测试因缺少 `extend` 行为失败。
- [ ] 实现 `MockDiscussionProvider.extend(session, batch_index)`，根据最近观点轮换角色生成回应、反驳、补充和主持人追问；批次长度固定为 8 便于 UI 阅读，但没有总批次上限。
- [ ] 运行测试确认通过，并保持初始 provider 的旧测试通过。

### Task 2: Live 播放与手动结束

**Files:**
- Modify: `brainstorm/playback.py`
- Modify: `brainstorm/session_controller.py`
- Test: `tests/test_persistence_playback.py`
- Test: `tests/test_generation_controller.py`

- [ ] 写失败测试：播放到末尾仍保持 live；`finish()` 才进入 completed；controller 追加后总 utterance 数增加且可继续播放。
- [ ] 运行对应测试确认红灯。
- [ ] 实现 `DiscussionPlayback.finish()`、live 末尾语义和 controller 的 `extend_discussion()`/`finish_discussion()`。
- [ ] 追加完成后重算机会档案，保存前保留全部记录；结束后发出 completed 信号。
- [ ] 运行 controller、playback 和全量测试。

### Task 3: 总结页和圆桌操作

**Files:**
- Modify: `brainstorm/qt_app.py`
- Modify: `brainstorm/qt_theme.py`
- Test: `tests/test_generation_controller.py`（必要时新增 Qt smoke case）

- [ ] 写失败测试或最小 Qt smoke 检查：页面存在“结束并总结”、总结页完整字段和返回圆桌信号。
- [ ] 实现 `SummaryPage`，展示机会档案全部字段、讨论统计、来源与生成状态。
- [ ] 圆桌页增加“结束并总结”、播放到末尾时的“继续讨论”提示、完整记录抽屉动画和更清晰的阶段状态。
- [ ] 确保历史加载直接可查看总结，不触发追加。
- [ ] 运行 Qt offscreen smoke test。

### Task 4: 大厅与窗口外壳响应式修整

**Files:**
- Modify: `brainstorm/qt_app.py`
- Modify: `brainstorm/qt_theme.py`
- Test: `tests/test_generation_controller.py`（必要时新增 UI smoke case）

- [ ] 将大厅角色面板放入滚动容器，限制输入区宽度并修正 1366×768/1536×864 下的拉伸策略。
- [ ] 增加显式退出、全屏/窗口化切换和统一 hover/disabled 状态。
- [ ] 保持暗色牌室材质，不引入白色默认控件。
- [ ] 运行 offscreen 截图或控件尺寸检查，确认九个角色和主按钮可见。

### Task 5: 文档、回归和桌面包

**Files:**
- Modify: `README.md`
- Modify: `nine-roundtable-stages.md`
- Run: `compileall`, full unittest, PyInstaller Qt spec

- [ ] 更新 README 说明无限讨论、手动总结和历史行为。
- [ ] 运行完整 `python -m unittest discover -s tests -v` 和 `python -m compileall -q brainstorm app.py tests`。
- [ ] 使用隔离 Qt runtime 重新构建 one-folder 包到新目录，不覆盖旧发布目录。
- [ ] 从桌面快捷方式启动，验证可见主窗口、总结页入口和资源加载。
