# 九人圆桌后台生成基础 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将讨论 provider 调用移出 Qt UI 线程，并提供可取消、可丢弃过期结果且能安全回退的生成流程。

**Architecture:** `SessionController` 创建 `_GenerationWorker` 并把它移动到 `QThread`；worker 只负责调用 provider，controller 槽负责 session、playback 和 UI 状态。每次启动使用递增 token，取消使用 `threading.Event`。

**Tech Stack:** Python 3.10+, PySide6 `QObject/QThread/Signal/Slot`, `threading.Event`, unittest。

---

### Task 1: Add worker/controller tests

**Files:**
- Modify: `tests/test_persistence_playback.py` or create `tests/test_generation_controller.py`
- Test: `tests/test_generation_controller.py`

- [ ] **Step 1: Write failing tests** for worker success, cancellation propagation, stale token discard, and ProviderFailure fallback.
- [ ] **Step 2: Run `python -m unittest tests.test_generation_controller -v` and verify the new tests fail because generation remains synchronous and no worker API exists.
- [ ] **Step 3: Keep the tests isolated from real network/model SDK by injecting deterministic provider objects and using `QCoreApplication`.

### Task 2: Implement threaded discussion generation

**Files:**
- Modify: `brainstorm/session_controller.py`
- Modify: `brainstorm/models.py` only if a generation metadata field is required by the tests.

- [ ] **Step 1: Add `_GenerationWorker` with `finished`, `failed`, and `cancelled` signals, a provider/topic/roles/source note payload, and a `threading.Event`.
- [ ] **Step 2: Add controller generation state, token checks, `generation_state_changed`, `generation_started`, and `cancel_generation()`.
- [ ] **Step 3: Move provider invocation into the worker and route all session/playback mutations back through controller slots.
- [ ] **Step 4: Implement safe Mock fallback for `ProviderFailure`, preserving the configured provider metadata accurately.
- [ ] **Step 5: Clean up thread references after exit and ignore stale worker signals.

### Task 3: Wire the existing Qt UI to generation state

**Files:**
- Modify: `brainstorm/qt_app.py`

- [ ] **Step 1: Connect generation state signals to the existing status label/control area.
- [ ] **Step 2: Disable duplicate start actions while generation is active and expose cancel through the existing control path if present.
- [ ] **Step 3: Keep playback controls disabled until `session_ready` arrives.

### Task 4: Verify and document

**Files:**
- Modify: `README.md` and `nine-roundtable-stages.md` only for claims that are now accurate.

- [ ] **Step 1: Run `python -m unittest discover -s tests -v`.
- [ ] **Step 2: Run `python -m compileall -q brainstorm app.py`.
- [ ] **Step 3: Run a Qt offscreen smoke test that starts a deterministic provider and confirms the event loop remains usable.
- [ ] **Step 4: Update stage memory with verified status and remaining limitations.
