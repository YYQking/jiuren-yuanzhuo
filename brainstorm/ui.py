"""Tkinter presentation layer for the offline roundtable."""

import math
import tkinter as tk
from tkinter import messagebox, ttk

from .engine import MockDiscussionProvider
from .models import ViewpointKind
from .roles import DEFAULT_ROLES


class BrainstormApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("九人圆桌 · 头脑风暴")
        self.geometry("1440x880")
        self.minsize(1100, 700)
        self.configure(bg="#eef1ed")
        self.provider = MockDiscussionProvider()
        self.role_vars = {role.id: tk.BooleanVar(value=True) for role in DEFAULT_ROLES}
        self.seat_items: dict[str, dict[str, int]] = {}
        self.active_seat_id: str | None = None
        self._build_style()
        self._build_ui()

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 20, "bold"), foreground="#17251f")
        style.configure("Sub.TLabel", font=("Microsoft YaHei UI", 10), foreground="#5b6b63")
        style.configure("Section.TLabel", font=("Microsoft YaHei UI", 12, "bold"), foreground="#17251f")
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"), foreground="#ffffff")

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(22, 18, 22, 10))
        header.pack(fill="x")
        ttk.Label(header, text="九人圆桌 · 头脑风暴", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="让不同社会视角充分碰撞，再把灵感收敛成可以验证的机会。当前为离线模拟模式。",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(4, 12))

        input_frame = ttk.LabelFrame(header, text="讨论主题", padding=10)
        input_frame.pack(fill="x")
        self.topic_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.topic_var, font=("Microsoft YaHei UI", 11)).pack(fill="x", pady=(0, 8))
        self.source_var = tk.StringVar()
        source_row = ttk.Frame(input_frame)
        source_row.pack(fill="x")
        ttk.Entry(source_row, textvariable=self.source_var).pack(side="left", fill="x", expand=True)
        ttk.Label(source_row, text="  可选：前沿消息/趋势线索（当前不联网）", style="Sub.TLabel").pack(side="left")
        button_row = ttk.Frame(input_frame)
        button_row.pack(fill="x", pady=(10, 0))
        ttk.Button(button_row, text="开始圆桌讨论", command=self.start_discussion).pack(side="left")
        ttk.Button(button_row, text="快速模式（4人）", command=self.quick_mode).pack(side="left", padx=8)
        ttk.Button(button_row, text="完整模式（9人）", command=self.all_roles).pack(side="left")
        ttk.Button(button_row, text="清空讨论", command=self.clear_discussion).pack(side="right")

        body = ttk.Frame(self, padding=(22, 4, 22, 18))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=0, minsize=270)
        body.columnconfigure(1, weight=3)
        body.columnconfigure(2, weight=2)
        body.rowconfigure(0, weight=1)

        self._build_roles(body)
        self._build_transcript(body)
        self._build_insights(body)

    def _build_roles(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="讨论席位（默认 9 人）", padding=10)
        box.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ttk.Label(box, text="主持人由系统负责，不占九个席位。", style="Sub.TLabel", wraplength=235).pack(anchor="w", pady=(0, 8))
        for role in DEFAULT_ROLES:
            row = ttk.Frame(box)
            row.pack(fill="x", pady=3)
            ttk.Checkbutton(
                row,
                text=role.name,
                variable=self.role_vars[role.id],
                command=self._refresh_seat_states,
            ).pack(side="left")
            ttk.Label(row, text=role.duty, style="Sub.TLabel", wraplength=155).pack(side="right", anchor="e")
        ttk.Separator(box).pack(fill="x", pady=10)
        ttk.Button(box, text="全选", command=self.all_roles).pack(side="left")
        ttk.Button(box, text="全不选", command=self.no_roles).pack(side="left", padx=6)
        ttk.Label(box, text="建议至少保留需求者、创业实践者和怀疑者。", style="Sub.TLabel", wraplength=235).pack(anchor="w", pady=(12, 0))

    def _build_transcript(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="九人圆桌现场", padding=8)
        box.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        box.rowconfigure(0, weight=3, minsize=280)
        box.rowconfigure(1, weight=2, minsize=150)
        box.columnconfigure(0, weight=1)

        self.roundtable_canvas = tk.Canvas(
            box,
            background="#263b32",
            highlightthickness=0,
            bd=0,
        )
        self.roundtable_canvas.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        self.roundtable_canvas.bind("<Configure>", self._layout_roundtable)

        record_frame = ttk.Frame(box)
        record_frame.grid(row=1, column=0, sticky="nsew")
        record_frame.rowconfigure(0, weight=1)
        record_frame.columnconfigure(0, weight=1)
        self.transcript = tk.Text(
            record_frame,
            wrap="word",
            state="disabled",
            font=("Microsoft YaHei UI", 10),
            bg="#fbfcfb",
            fg="#17251f",
            relief="flat",
            padx=12,
            pady=10,
        )
        scroll = ttk.Scrollbar(record_frame, orient="vertical", command=self.transcript.yview)
        self.transcript.configure(yscrollcommand=scroll.set)
        self.transcript.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.transcript.tag_configure("speaker", font=("Microsoft YaHei UI", 10, "bold"), foreground="#17251f")
        self.transcript.tag_configure("meta", foreground="#64746c", font=("Microsoft YaHei UI", 9))
        self.transcript.tag_configure("moderator", foreground="#8a641d")
        self.transcript.tag_configure("risk", foreground="#b33a32")
        self.transcript.tag_configure("opportunity", foreground="#18734b")
        self.transcript.tag_configure("validation", foreground="#a56a16")

        self._draw_roundtable()

    def _build_insights(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="前沿线索与机会卡", padding=10)
        box.grid(row=0, column=2, sticky="nsew")
        box.rowconfigure(4, weight=1)
        box.columnconfigure(0, weight=1)
        self.source_display = tk.Text(box, height=5, wrap="word", state="disabled", font=("Microsoft YaHei UI", 9), bg="#f3f6f3", relief="flat", padx=8, pady=8)
        self.source_display.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(box, text="主持人提炼", style="Section.TLabel").grid(row=1, column=0, sticky="w")
        self.insight_display = tk.Text(box, height=12, wrap="word", state="disabled", font=("Microsoft YaHei UI", 10), bg="#fbfcfb", relief="flat", padx=8, pady=8)
        self.insight_display.grid(row=2, column=0, sticky="ew", pady=(5, 10))
        ttk.Label(box, text="机会卡 / 下一步", style="Section.TLabel").grid(row=3, column=0, sticky="nw")
        self.opportunity_display = tk.Text(box, wrap="word", state="disabled", font=("Microsoft YaHei UI", 10), bg="#fbfcfb", relief="flat", padx=8, pady=8)
        self.opportunity_display.grid(row=4, column=0, sticky="nsew", pady=(5, 0))

    def _draw_roundtable(self) -> None:
        canvas = self.roundtable_canvas
        canvas.delete("all")
        self.seat_items.clear()
        self.table_items = {
            "shadow": canvas.create_oval(0, 0, 1, 1, fill="#182820", outline=""),
            "rim": canvas.create_oval(0, 0, 1, 1, fill="#8c6a2e", outline="#b99a55", width=1),
            "felt": canvas.create_oval(0, 0, 1, 1, fill="#164734", outline="#0c2f25", width=2),
            "inner": canvas.create_oval(0, 0, 1, 1, fill="#1b553e", outline="#326d52", width=1),
            "title": canvas.create_text(0, 0, text="主持人", fill="#f2dfae", font=("Microsoft YaHei UI", 12, "bold")),
            "topic": canvas.create_text(0, 0, text="等待输入讨论主题", fill="#e7f0e8", font=("Microsoft YaHei UI", 10), width=220),
            "status": canvas.create_text(0, 0, text="准备就绪", fill="#b7cdbb", font=("Microsoft YaHei UI", 9)),
        }
        for role in DEFAULT_ROLES:
            self.seat_items[role.id] = {
                "card": canvas.create_rectangle(0, 0, 1, 1, fill="#315548", outline="#75907e", width=1),
                "halo": canvas.create_oval(0, 0, 1, 1, fill="#315548", outline="", state="hidden"),
                "avatar": canvas.create_oval(0, 0, 1, 1, fill=role.color, outline="#f4ead0", width=2),
                "initials": canvas.create_text(0, 0, text=self._avatar_text(role.name), fill="#ffffff", font=("Microsoft YaHei UI", 10, "bold")),
                "name": canvas.create_text(0, 0, text=role.name, fill="#f4f7f1", font=("Microsoft YaHei UI", 9, "bold")),
                "state": canvas.create_text(0, 0, text="参与", fill="#bdd1c3", font=("Microsoft YaHei UI", 8)),
            }
        self._layout_roundtable()

    @staticmethod
    def _avatar_text(name: str) -> str:
        return name[:2] if len(name) > 1 else name

    def _layout_roundtable(self, _event=None) -> None:
        canvas = self.roundtable_canvas
        width = max(canvas.winfo_width(), 360)
        height = max(canvas.winfo_height(), 250)
        cx, cy = width / 2, height * 0.49
        table_rx = max(115, min(width * 0.34, width / 2 - 55))
        table_ry = max(76, min(height * 0.34, height / 2 - 26))
        canvas.coords(self.table_items["shadow"], cx - table_rx - 6, cy - table_ry + 8, cx + table_rx + 6, cy + table_ry + 8)
        canvas.coords(self.table_items["rim"], cx - table_rx, cy - table_ry, cx + table_rx, cy + table_ry)
        canvas.coords(self.table_items["felt"], cx - table_rx + 7, cy - table_ry + 7, cx + table_rx - 7, cy + table_ry - 7)
        canvas.coords(self.table_items["inner"], cx - table_rx + 18, cy - table_ry + 18, cx + table_rx - 18, cy + table_ry - 18)
        canvas.coords(self.table_items["title"], cx, cy - 17)
        canvas.coords(self.table_items["topic"], cx, cy + 5)
        canvas.coords(self.table_items["status"], cx, cy + 29)

        seat_rx = max(135, min(width * 0.43, width / 2 - 38))
        seat_ry = max(82, min(height * 0.43, height / 2 - 22))
        card_w = max(82, min(128, width * 0.15))
        card_h = 56 if height >= 330 else 48
        avatar_r = max(14, min(22, card_h * 0.36))
        name_font = max(8, min(10, int(width / 115)))
        state_font = max(7, min(8, int(width / 145)))

        for index, role in enumerate(DEFAULT_ROLES):
            angle = (2 * math.pi * index / len(DEFAULT_ROLES)) - math.pi / 2
            x = cx + math.cos(angle) * seat_rx
            y = cy + math.sin(angle) * seat_ry
            items = self.seat_items[role.id]
            canvas.coords(items["card"], x - card_w / 2, y - card_h / 2, x + card_w / 2, y + card_h / 2)
            canvas.coords(items["halo"], x - avatar_r - 6, y - avatar_r - 6, x + avatar_r + 6, y + avatar_r + 6)
            canvas.coords(items["avatar"], x - avatar_r, y - avatar_r, x + avatar_r, y + avatar_r)
            canvas.coords(items["initials"], x, y)
            canvas.coords(items["name"], x, y + avatar_r + 9)
            canvas.coords(items["state"], x, y + avatar_r + 22)
            canvas.itemconfigure(items["name"], font=("Microsoft YaHei UI", name_font, "bold"))
            canvas.itemconfigure(items["state"], font=("Microsoft YaHei UI", state_font))
        self._refresh_seat_states()

    def _refresh_seat_states(self) -> None:
        if not self.seat_items:
            return
        for role in DEFAULT_ROLES:
            items = self.seat_items[role.id]
            selected = self.role_vars[role.id].get()
            active = role.id == self.active_seat_id
            if selected:
                fill = "#315548"
                outline = "#d8c17c" if active else "#75907e"
                text = "当前发言" if active else "参与"
                text_color = "#f3e5ae" if active else "#bdd1c3"
                avatar_fill = role.color
            else:
                fill = "#35433d"
                outline = "#66746d"
                text = "未参与"
                text_color = "#9da9a2"
                avatar_fill = "#69756e"
            self.roundtable_canvas.itemconfigure(items["card"], fill=fill, outline=outline, width=2 if active else 1)
            self.roundtable_canvas.itemconfigure(items["avatar"], fill=avatar_fill, outline="#f4ead0" if selected else "#9ba59f")
            self.roundtable_canvas.itemconfigure(items["name"], fill="#f4f7f1" if selected else "#aab5ae")
            self.roundtable_canvas.itemconfigure(items["state"], text=text, fill=text_color)
            self.roundtable_canvas.itemconfigure(items["halo"], state="normal" if active else "hidden", outline="#e4c66f", width=2)

    def _set_active_seat(self, speaker_id: str | None) -> None:
        self.active_seat_id = speaker_id if speaker_id in self.seat_items else None
        self._refresh_seat_states()

    def _set_center_status(self, status: str) -> None:
        if hasattr(self, "table_items"):
            self.roundtable_canvas.itemconfigure(self.table_items["status"], text=status)

    @staticmethod
    def _set_text(widget: tk.Text, content: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")

    def start_discussion(self) -> None:
        selected = [role for role in DEFAULT_ROLES if self.role_vars[role.id].get()]
        try:
            session = self.provider.discuss(self.topic_var.get(), selected, self.source_var.get())
        except ValueError as exc:
            messagebox.showwarning("还需要一点信息", str(exc))
            return
        self._set_text(self.transcript, "")
        self._set_active_seat(None)
        self.roundtable_canvas.itemconfigure(self.table_items["topic"], text=self.topic_var.get().strip())
        self._set_center_status("讨论进行中")
        for utterance in session.utterances:
            if utterance.speaker_id == "moderator":
                self._set_center_status("主持人正在收敛观点")
            else:
                self._set_active_seat(utterance.speaker_id)
                self._set_center_status(f"{utterance.speaker_name} 正在发言")
            tag = "moderator" if utterance.speaker_id == "moderator" else "speaker"
            if utterance.kind == ViewpointKind.RISK:
                tag = "risk"
            elif utterance.kind == ViewpointKind.OPPORTUNITY:
                tag = "opportunity"
            elif utterance.kind == ViewpointKind.VALIDATION:
                tag = "validation"
            self.transcript.configure(state="normal")
            self.transcript.insert("end", f"【{utterance.phase}】 {utterance.speaker_name}  ·  {utterance.kind.value}\n", (tag,))
            self.transcript.insert("end", f"{utterance.content}\n\n")
            self.transcript.configure(state="disabled")
        self.transcript.see("end")
        self._set_center_status("讨论完成，可继续追问")
        source = self.source_var.get().strip() or "暂无外部消息。你可以把看到的政策、新闻或数据粘贴到这里作为讨论线索。"
        self._set_text(self.source_display, f"当前素材（未联网、未核验）\n{source}")
        opportunity = session.opportunity
        self._set_text(self.opportunity_display, self._format_opportunity(opportunity))
        self._set_text(self.insight_display, "讨论共识：先从具体场景和小范围用户开始。\n\n主要分歧：需求强度、行业阻力、技术复杂度和差异化。\n\n提醒：角色发言是模拟观点，不等于市场事实。")

    @staticmethod
    def _format_opportunity(card) -> str:
        lines = [f"机会方向：{card.title}", f"目标用户：{card.audience}", "", "支持理由："]
        lines.extend(f"• {item}" for item in card.support)
        lines.append("\n主要风险：")
        lines.extend(f"• {item}" for item in card.risks)
        lines.append("\n待验证假设：")
        lines.extend(f"• {item}" for item in card.assumptions)
        lines.append("\n建议下一步：")
        lines.extend(f"• {item}" for item in card.next_steps)
        lines.append(f"\n观点分布：{card.stance_counts}")
        return "\n".join(lines)

    def clear_discussion(self) -> None:
        for widget in (self.transcript, self.source_display, self.insight_display, self.opportunity_display):
            self._set_text(widget, "")
        self._set_active_seat(None)
        self.roundtable_canvas.itemconfigure(self.table_items["topic"], text="等待输入讨论主题")
        self._set_center_status("准备就绪")

    def all_roles(self) -> None:
        for var in self.role_vars.values():
            var.set(True)
        self._refresh_seat_states()

    def no_roles(self) -> None:
        for var in self.role_vars.values():
            var.set(False)
        self._refresh_seat_states()

    def quick_mode(self) -> None:
        chosen = {"trend", "need", "builder", "skeptic"}
        for role_id, var in self.role_vars.items():
            var.set(role_id in chosen)
        self._refresh_seat_states()


def run() -> None:
    app = BrainstormApp()
    app.mainloop()
