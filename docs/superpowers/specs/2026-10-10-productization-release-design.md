# D 阶段：产品化与发布验证设计

## 目标

把 C 阶段的后台生成实现收紧为可交付版本：取消后旧 worker 的结果不能污染新会话，应用关闭和返回大厅时能安全收尾，并完成 Qt 启动与 one-folder 发布包验证。

## 范围与验收标准

1. `SessionController.cancel_generation()` 立即使当前 generation token 失效；即使 provider 忽略取消事件，迟到的 `finished`、`failed` 和 partial 信号也不能改变当前会话。
2. 新建、加载历史、返回大厅和关闭窗口都触发取消/失效语义；取消状态对用户显示为“正在取消”后“生成已取消”。
3. 在当前 Python 环境运行完整非 Qt 测试；PySide6 缺失时，Qt 测试必须明确跳过而不是静默消失。
4. 使用现有 Qt one-folder 包做启动级检查；如果本机没有 PyInstaller/PySide6，记录限制，不伪称完成真实 Qt smoke test。
5. 新发布产物只写入 `build-stage-d` 和 `dist-stage-d`，不得覆盖 `dist-final`、`build-final` 或 `build-stage-b`。

## 实现边界

- 不改变离线默认策略、RSS opt-in 或真实模型 opt-in；v4 数据只增加可向后兼容的 RSS 状态字段。
- 不记录 API key、请求头、原始异常或网络细节。
- one-folder 是 D 阶段发布目标；one-file 留给后续阶段。

## 验证策略

- 用 provider 忽略取消事件的回归测试证明 token 失效先于 worker 返回。
- 运行 `python -m unittest discover -s tests -v` 和 `python -m compileall -q brainstorm app.py tests`。
- 使用隔离 PySide6 运行时执行 Qt worker/取消/关闭生命周期测试，并在最终 one-folder exe 上设置 `QT_QPA_PLATFORM=offscreen` 做短时启动检查。
- 使用 PyInstaller 输出到新的 `dist-stage-d` 与 `build-stage-d`，核对入口、Qt 平台插件和头像资源。
