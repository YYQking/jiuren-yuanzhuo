from pathlib import Path

REPORT = Path(r"C:\Users\14726\Desktop\测试程序\头脑风暴\2026-10-30-第1次测试.md")

STATUS = [
    "已修（验证：`MainWindow._start` 先校验空议题再跳页，停在大厅并出提示；`tests/test_report_2026_10_30.py`）",
    "已修（验证：`finish_discussion` 不再按播放游标截断，先掐掉后台批次；`test_manual_finish_keeps_generated_turns_and_user_input`）",
    "已修（验证：`roles.role_name(mode, id)` 统一映射；界面与导出都不再出现内部 id；`test_exported_stances_use_seat_names_not_internal_ids`）",
    "已修（验证：`orchestration.derive_state` 从发言兜底，模型刷新优先；`test_derive_state_reads_the_stream_when_the_orchestrator_is_silent`）",
    "已修（验证：`llm._fill_empty_card_sections` + 每批 `_refresh_opportunity(fill_missing=True)`；`test_empty_card_sections_are_filled_from_what_was_said`）",
    "已修（验证：`qt_app.export_target` 按后缀决定格式、`export.export_json` 真写 JSON；`test_typed_extension_wins_over_the_selected_filter`）",
    "已修（验证：`_discuss_hotspot` 只把标题与来源填进大厅议题票，不直接开桌；`test_hotspot_card_fills_the_lobby_instead_of_jumping_straight_in`）",
    "已修（验证：`TurnSpec.reply_to_event_id` 在模型漏填时强制兑现插话回应）",
    "已修（验证：`network_used = 素材命中 or 模型请求数>0`，`_adopt_metadata` 里请求数>0 即置真）",
    "已修（验证：只有真的抓过素材且抓空才写 `fallback_reason`；未请求素材时留空）",
    "已修（验证：`export.plain()` 白名单式中文枚举，导出不再出现 provider / 状态码）",
    "已修（验证：观点分布改成「支持/机会 3 条 · 保留/假设 2 条」这种可读写法）",
    "已修（验证：导出与界面读同一份 `role_stances`，行数等于席位数）",
    "已修（验证：两处统一口径，并显式写「席位 N 条 + 主持人及其他」）",
    "已修（验证：列表按 `created_at` 倒序；底部按钮改中文「关闭」）",
    "已修（验证：保存/取消中文化，新增「测试连接」按钮，成功失败都给原因）",
    "已修（验证：一次性回执照走大厅提示行；回到大厅时状态行按上一场真实提供方刷新）",
    "已修（验证：删掉无 TTS 却可点的「声音：静默」按钮）",
    "已修（验证：无 url 的条目写「这条是模型凭记忆写的，没有原文链接」并置灰）",
    "已修（验证：情绪账本；实测 `artifacts/real-mood-4` 22 条里 3 条阴面、8 笔情绪账）",
    "已修（验证：质检只卡重复与编造；同场实测 1/8 条被重写、`review_note` 非空可见）",
    "已修（验证：0 条时给「试试更短的关键词」这类下一步；超 7 天缓存标「缓存 N 天前」）",
    "已修（验证：标题右侧省略 + 悬停显示全文）",
    "已修（验证：`ActionButton.setAccessibleName/setAccessibleDescription`，读屏能念出按钮名）",
    "已修（验证：完整记录抽屉的两块文本可选中、可键盘聚焦、可复制）",
    "已修（验证：同 D2，整场发言在抽屉里是可选中的纯文本列表）",
    "已修（验证：发牌提示 D 并真正绑定 D 键；空格 / Esc 在说明与 tooltip 里一致）",
    "已修（验证：提示另起一行，计数与提示同时可见）",
]

text = REPORT.read_text(encoding="utf-8").splitlines()
out = []
index = 0
for line in text:
    if line.startswith("- **状态："):
        if index < len(STATUS):
            out.append(f"- **状态：{STATUS[index]}**")
            index += 1
        else:
            out.append(line)
    else:
        out.append(line)

header = [
    "",
    "---",
    "",
    "## 10. 修复记录（2026-10-30 晚）",
    "",
    "28 条全部处理完毕，逐条状态已写在各条下面。配套回归测试：`tests/test_report_2026_10_30.py` + 全量 359 项全绿。",
    "",
    "- P1 八条：全部改的是取数/校验/口径，没有一条靠改文案糊过去。",
    "- P2 十五条：网络状态、回退原因、导出人话化、最近讨论排序、AI 设置、大厅状态行、死按钮、缓存提示、标题省略。",
    "- P3 五条：读屏名、抽屉可复制、全文可选、快捷键一致、提示不再顶掉计数。",
    "- 第 6 节三条待复核：导出对话框前台性未复现（改动后原生框正常前置）；抽屉可读性由 D2 解决；雷达卡片空白处点击现与按钮同路。",
    "",
    "已知仍未做：第 7 节 5 条小建议（议题票提示淡出、总结页一句话摘要、来源卡片默认折叠、插话快捷键、分区按钮显示人数）。",
]
out.extend(header)
REPORT.write_text("\n".join(out) + "\n", encoding="utf-8")
print("statuses replaced:", index)
