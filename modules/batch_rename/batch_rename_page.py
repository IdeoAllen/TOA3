# -*- coding: utf-8 -*-
"""批量重命名页：交付预设、冲突门禁、撤销、打包链式提示。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_info, show_warning
from modules.batch_rename.rename_service import (
    PRESETS,
    apply_rename,
    apply_undo,
    load_undo_map,
    preview_rename,
    save_undo_map,
)
from services.storage_paths import module_data_dir
from widgets import (
    ComboBox,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
    SpinBox,
)


class BatchRenamePage(BasePage):
    page_id = "batch_rename"
    page_title = "批量重命名"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._plan_pairs: list[tuple[Path, Path]] = []
        self._has_conflict = False
        self._previewed = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)
        scroll.add_widget(
            PageHeader(
                "批量重命名",
                "交付照片/课件编号：选预设 → 预览（冲突红字禁止执行）→ 执行；可撤销本轮。",
            )
        )

        box = FormSection("规则")
        row = QHBoxLayout()
        self._folder = LineEdit()
        row.addWidget(self._folder, 1)
        btn = SecondaryButton("选择目录")
        btn.clicked.connect(self._pick)
        row.addWidget(btn)
        box.add_layout(row)

        row_p = QHBoxLayout()
        row_p.addWidget(HintLabel("交付预设"))
        self._preset = ComboBox()
        self._preset.addItem("（自定义）", "")
        for key, meta in PRESETS.items():
            self._preset.addItem(str(meta["label"]), key)
        self._preset.currentIndexChanged.connect(self._apply_preset)
        row_p.addWidget(self._preset, 1)
        box.add_layout(row_p)

        self._pattern = LineEdit("*")
        self._prefix = LineEdit()
        self._suffix = LineEdit()
        self._find = LineEdit()
        self._replace = LineEdit()
        self._start = SpinBox()
        self._start.setRange(0, 99999)
        self._start.setValue(1)
        for label, w in (
            ("匹配 glob", self._pattern),
            ("前缀（{n} / {n:02d}）", self._prefix),
            ("后缀", self._suffix),
            ("查找", self._find),
            ("替换", self._replace),
            ("起始序号", self._start),
        ):
            box.add_widget(HintLabel(label))
            box.add_widget(w)
            if hasattr(w, "textChanged"):
                w.textChanged.connect(self._invalidate_preview)
            if w is self._start:
                w.valueChanged.connect(self._invalidate_preview)

        actions = QHBoxLayout()
        btn_prev = SecondaryButton("预览")
        btn_prev.clicked.connect(self._preview)
        actions.addWidget(btn_prev)
        self._btn_run = PrimaryButton("执行重命名")
        self._btn_run.clicked.connect(self._run)
        self._btn_run.setEnabled(False)
        actions.addWidget(self._btn_run)
        self._btn_undo = SecondaryButton("撤销本轮")
        self._btn_undo.clicked.connect(self._undo)
        actions.addWidget(self._btn_undo)
        self._btn_pack = SecondaryButton("去打包归档…")
        self._btn_pack.clicked.connect(self._goto_packager)
        self._btn_pack.setVisible(False)
        actions.addWidget(self._btn_pack)
        actions.addStretch(1)
        box.add_layout(actions)

        self._conflict_hint = HintLabel("")
        box.add_widget(self._conflict_hint)
        self._preview_box = ReadOnlyPlainTextEdit()
        self._preview_box.setMinimumHeight(200)
        box.add_widget(self._preview_box)
        box.add_widget(HintLabel("必须先预览且无冲突才能执行。改完后可去「文件打包归档」。"))
        scroll.add_widget(box)
        scroll.add_stretch(1)
        self.apply_page_focus_policy()

    def primary_focus_widget(self) -> QWidget | None:
        return self._folder

    def _undo_path(self) -> Path:
        return Path(module_data_dir(self.page_id, create=True)) / "last_rename.json"

    def _invalidate_preview(self, *_args) -> None:
        self._previewed = False
        self._plan_pairs = []
        self._has_conflict = False
        self._btn_run.setEnabled(False)
        self._conflict_hint.setText("规则已变更，请重新预览。")

    def _apply_preset(self) -> None:
        key = str(self._preset.currentData() or "")
        if not key or key not in PRESETS:
            return
        meta = PRESETS[key]
        self._pattern.setText(str(meta.get("pattern") or "*"))
        self._prefix.setText(str(meta.get("prefix") or ""))
        self._suffix.setText(str(meta.get("suffix") or ""))
        self._find.setText(str(meta.get("find") or ""))
        self._replace.setText(str(meta.get("replace") or ""))
        self._start.setValue(int(meta.get("start") or 1))
        self._invalidate_preview()

    def _pick(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择目录")
        if d:
            self._folder.setText(d)
            self._invalidate_preview()

    def _preview(self) -> None:
        folder = self._folder.text().strip()
        if not folder:
            show_warning(self, "请选择目录。")
            return
        plan = preview_rename(
            folder,
            pattern=self._pattern.text().strip() or "*",
            prefix=self._prefix.text(),
            suffix=self._suffix.text(),
            find=self._find.text(),
            replace=self._replace.text(),
            start_index=int(self._start.value()),
        )
        self._plan_pairs = plan.pairs
        self._has_conflict = plan.has_conflict
        self._previewed = True
        lines: list[str] = []
        if plan.conflicts:
            lines.append("【冲突 · 禁止执行】")
            lines.extend(plan.conflicts)
            lines.append("")
        for a, b in plan.pairs:
            lines.append(f"{a.name}  →  {b.name}")
        if not plan.pairs and not plan.conflicts:
            lines.append("（无变更）")
        self._preview_box.setPlainText("\n".join(lines))
        if plan.has_conflict:
            self._conflict_hint.setText(f"发现 {len(plan.conflicts)} 处冲突，请调整规则后重预览。")
            self._btn_run.setEnabled(False)
            self.report_status("预览有冲突", level=StatusLevel.WARNING)
        elif not plan.pairs:
            self._conflict_hint.setText("没有需要重命名的文件。")
            self._btn_run.setEnabled(False)
            self.report_status("预览 0 项")
        else:
            self._conflict_hint.setText(f"预览通过 · {len(plan.pairs)} 项可执行")
            self._btn_run.setEnabled(True)
            self.report_status(f"预览 {len(plan.pairs)} 项")

    def _run(self) -> None:
        if not self._previewed:
            show_warning(self, "请先预览。")
            return
        if self._has_conflict:
            show_warning(self, "存在冲突，禁止执行。")
            return
        if not self._plan_pairs:
            show_warning(self, "没有需要重命名的文件。")
            return

        def _do() -> None:
            ok, errors, mapping = apply_rename(self._plan_pairs)
            if mapping:
                save_undo_map(self._undo_path(), mapping)
            msg = f"成功 {ok} 个"
            if errors:
                msg += "\n" + "\n".join(errors[:20])
            if ok:
                show_info(self, msg + "\n\n可「撤销本轮」，或点「去打包归档」继续整理。")
                self._btn_pack.setVisible(True)
                self.report_status(f"重命名完成 {ok}", level=StatusLevel.SUCCESS)
            else:
                show_warning(self, msg)
                self.report_status("重命名失败", level=StatusLevel.ERROR)
            self._invalidate_preview()
            self._preview_box.setPlainText(msg)

        self.run_safe(_do, title="重命名失败")

    def _undo(self) -> None:
        pairs = load_undo_map(self._undo_path())
        if not pairs:
            show_warning(self, "没有可撤销的本轮记录。")
            return

        def _do() -> None:
            ok, errors = apply_undo(pairs)
            msg = f"已撤销 {ok} 个"
            if errors:
                msg += "\n" + "\n".join(errors[:20])
            if ok:
                try:
                    self._undo_path().unlink(missing_ok=True)
                except OSError:
                    pass
                show_info(self, msg)
                self.report_status(f"已撤销 {ok}", level=StatusLevel.SUCCESS)
            else:
                show_warning(self, msg)
            self._invalidate_preview()

        self.run_safe(_do, title="撤销失败")

    def _goto_packager(self) -> None:
        win = self.window()
        nav = getattr(win, "navigate", None)
        if callable(nav):
            nav("file_packager")
            self.report_status("已打开文件打包归档")
        else:
            show_info(self, "请到顶栏「文件」→「文件打包归档」。")

    def on_enter(self) -> None:
        self.report_status("批量重命名 · 交付预设 / 冲突门禁 / 撤销")
