from pathlib import Path

p = Path(r"C:\Users\14726\项目\九人圆桌-源码\PROJECT_MEMORY.md")
t = p.read_text(encoding="utf-8")
marker = "没有本文件之外的自动继续任务；以用户下一条请求为准。不要声称所有设计目标已完美实现。"
assert marker in t
section = """## 18. 第 1 次黑盒测试报告的 28 条（2026-10-30）

**报告来源。** `C:\\Users\\14726\\Desktop\\测试程序\\头脑风暴\\2026-10-30-第1次测试.md`，28 条问题（P1 8 / P2 15 / P3 5）+ 26 条「已验证正常勿回退」。报告里没有源码，只有现象、复现和断言；逐条状态已经回写进那份文件。

**P1 八条改的都是取数与入口，不是文案。**
- B1 空议题：校验前移到 `MainWindow._start` 第一行，所有入口共用；提示走 `LobbyPage.notify` 的独立提示行。
- B2「结束就丢发言」真凶在 `session_controller.finish_discussion`：按播放游标截断 `utterances`。删掉截断，先 `_cancel_batch` 再 `rebuild_state`，一按结束就不会再有后台批次偷偷追加上来（顺带解决 C6 的「两处条数不一致」）。
- B3 立场轨迹：新增 `roles.role_name(mode, role_id)`，界面与 `export.py` 都过这一层。
- B4 共识/分歧/未答：`orchestration.derive_state(session)` 从发言的 intent 兜底（challenge→分歧、question→未答、support/synthesize→共识；主持人状态整理优先），只在模型留空时补。
- B5 六项空栏：`llm._fill_empty_card_sections` 按 `ViewpointKind` 从已说过的发言里收点；`_refresh_opportunity(fill_missing=True)` 每批补一次，已有内容一律不动。
- B6 假 JSON：`qt_app.export_target(path, selected)` 让后缀优先于下拉框，配 `export.export_json`。
- B7 热点卡片：`_discuss_hotspot` 只填议题票与来源并停在大厅，不再直接开桌。
- B8 插话没人应：`TurnSpec.reply_to_event_id`，模型漏填时由计划值兜底。

**P2/P3 里值得记住的几处**
- C1「未使用网络」：`network_used = 素材命中 or 模型请求数>0`（`_adopt_metadata` 里请求数>0 就置真）。这是 `network_used` 语义问题，不是文案问题。
- C2 回退原因污染：只有「真的抓过素材且抓空」才写 `fallback_reason`；没请求素材时清空。
- C3/C4 导出人话化：`export.plain()` + `MODE_IN_PLAIN_WORDS`/`STATUS_IN_PLAIN_WORDS`/`PROVIDER_IN_PLAIN_WORDS`；观点分布从 dict 原文改成「支持/机会 3 条 · …」。
- C9 大厅状态行：一次性回执走 `lobby.notify`（独立提示行）；回到大厅时 `_refresh_lobby_state_note()` 按上一场真实提供方刷新。
- C12 脸色：情绪账本已解决，实测 `artifacts/real-mood-4` 22 条 3 条阴面。
- C13 质检标记：收窄后的规则会真的打回，实测同场 1/8 条重写、`review_note` 非空。
- D1 读屏：`ActionButton.setAccessibleName/setAccessibleDescription`，`setText`/`set_hint` 同步。
- D2/D3：抽屉两块 `QTextEdit` 设 `TextSelectableByMouse|TextSelectableByKeyboard` + `StrongFocus`。
- D5：`LobbyPage.notice` 是独立一行，不再占「桌上 N 张」的计数标签。

**新增测试 `tests/test_report_2026_10_30.py`。** 覆盖 B3/B4/B5/B6 + 离线六项不空。写的时候踩到两个坑：`DiscussionSession` 没有 `roles=` 参数（用 `selected_role_ids=` + `mode=`）；`MockDiscussionProvider.discuss` 的签名是 `(topic, roles)` 而不是 `(session, ...)`。

**测试 352 → 359 全绿，28 条状态全部回写。**

"""
t = t.replace(marker, section + marker)
p.write_text(t, encoding="utf-8")
print("ok", len(t))
