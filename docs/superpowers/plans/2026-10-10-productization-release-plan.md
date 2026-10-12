# D 阶段产品化与发布验证实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 验证并收紧后台生成生命周期，完成 Qt 启动检查和独立发布产物记录。

**Architecture:** Controller 用 token 作为结果接收资格；取消先失效 token、再通知 worker。发布验证沿用 Qt one-folder 包，并使用独立的 stage-d 输出目录。

**Tech Stack:** Python 3.12、PySide6、unittest、PyInstaller（若环境提供）。

---

### Task 1: 取消竞态保护

**Files:**
- Modify: `brainstorm/session_controller.py`
- Test: `tests/test_generation_controller.py`

- [x] 增加忽略取消事件的 provider 回归测试。
- [x] 在取消入口先递增 token，再设置 worker 的取消事件。
- [x] 运行生成控制器测试；无 PySide6 时确认测试明确 skipped。

### Task 2: 完整回归和静态编译

**Files:**
- Verify: `tests/`
- Verify: `brainstorm/`

- [x] 运行 `python -m unittest discover -s tests -v`，记录通过数和 Qt skipped 数。
- [x] 运行 `python -m compileall -q brainstorm app.py tests`。

### Task 3: Qt 启动和发布目录

**Files:**
- Create: `docs/superpowers/specs/2026-10-10-productization-release-design.md`
- Create: `docs/superpowers/plans/2026-10-10-productization-release-plan.md`
- Create when tooling is available: `build-stage-d/`, `dist-stage-d/`

- [x] 用现有 one-folder exe 做短时 offscreen 启动检查。
- [x] 使用隔离 PySide6/PyInstaller 完成真实 Qt 生命周期测试。
- [x] 使用 `--distpath dist-stage-d --workpath build-stage-d` 生成 one-folder 包。
- [x] 核对入口 exe、Qt 平台插件和 `_internal/assets/avatars` 均存在，并完成 offscreen 启动检查。
