# 九人圆桌后台生成基础设计

## 目标

把讨论 provider 调用从 Qt 主线程移到 `QThread`，使启用真实模型或慢速 provider 时界面保持响应，同时保留离线 Mock、RSS 抓取、失败回退和播放流程。

## 范围

- 为讨论生成增加独立 worker 和线程生命周期管理。
- 用 generation token 丢弃过期 worker 的结果。
- 用取消事件终止支持取消的 provider 请求。
- 增加生成状态信号，供 Qt 界面显示忙碌、完成、取消和失败。
- ProviderFailure 继续安全回退到 Mock；不把失败结果标记为真实模型。
- 保持现有新闻 worker、session 持久化和播放 API 兼容。

## 组件与数据流

`SessionController.start()` 递增 token，整理 RSS 结果后创建 `_GenerationWorker`。worker 只调用 provider，并发出 `finished` 或 `failed`；controller 在自己的线程槽中检查 token，再设置 session 元数据、启动 playback、保存和发出 UI 信号。controller 的 `cancel_generation()` 设置当前 worker 的 `threading.Event`，随后旧 worker 的结果因 token 或取消状态被忽略。

离线 Mock 也经过同一 worker 路径，保证线程边界一致；由于 Mock 无阻塞，用户体验不变。新闻抓取完成后才启动生成 worker。新的 `start()` 会递增 token、停止旧线程的接收资格，并清理 pending 状态。

## 错误与取消

- 参数错误通过 `error` 信号返回，不创建 session。
- `ProviderFailure` 触发 Mock 回退，并将 `generation_status` 设为 `fallback`，记录安全的 `fallback_reason`。
- 用户取消时发出 `generation_state_changed("cancelled")`，不覆盖已有 session；已生成的旧结果不会进入当前 session。
- 线程退出后清空 worker/thread 引用，避免 stale worker 泄漏。
- 不记录 API Key、请求头、原始异常或网络细节。

## 验证

- worker 成功结果进入 controller 并触发 `session_ready`。
- 取消事件能被 provider 观察到。
- 新一轮 start 后旧 worker 结果被丢弃。
- ProviderFailure 安全回退到 Mock。
- 现有持久化、播放、RSS 和离线测试继续通过。
