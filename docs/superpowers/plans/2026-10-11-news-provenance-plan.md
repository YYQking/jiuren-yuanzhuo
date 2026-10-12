# 联网与观点来源实施计划

执行方式：在当前会话连续实施；项目无 Git 仓库，无提交步骤。使用 writing-plans、test-driven-development 和 verification-before-completion 流程。

**目标：** 默认可获取新闻，完整追溯素材，诚实解释九人语言来源。

**结构：** config 定义默认新闻源；news 筛选与排序；controller 传递结构化来源；engine/llm 区分模板与模型；models 提供统一观点来源解释；UI 和 export 复用解释。

- [x] 核对需求、现有代码和已有测试，修正测试中的非 ASCII bytes 字面量。
- [x] 为中文关键词匹配和跨 feed 排序添加失败测试，再修改 news.py，运行 tests.test_b_integration。
- [ ] 为 RSS/user 来源分离和模型来源上下文添加失败测试；修改 engine.py、llm.py、session_controller.py，将 sources 作为独立参数传入。
- [ ] 为默认联网、offline 边界和观点来源展示添加失败测试；修改 qt_app.py、models.py 和 export.py。
- [ ] 检查公开来源实际可访问性，选择有中文社会/经济/科技报道的有效来源；更新 config.py、README.md 和阶段记忆。
- [ ] 使用项目隔离运行时运行 compileall 和全部 unittest；用 tools/verify_ui.py 生成并检查 1366×768、1024×640 等界面截图。
- [ ] 使用 Qt spec 在 dist-network / build-network 构建；验证可见主窗口、头像资源；保存验证记录并告知用户实际限制。
