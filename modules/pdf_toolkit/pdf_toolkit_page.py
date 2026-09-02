# -*- coding: utf-8 -*-
"""PDF 工具页：合并 / 拆分 / 按页提取。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.pdf_toolkit.pdf_service import (
    default_stamp,
    extract_pages,
    inspect_pdf,
    merge_pdfs,
    parse_page_spec,
    split_pdf,
)
from services.storage_paths import module_output_dir
from widgets import (
    FormSection,
    HintLabel,
    LineEdit,
    ListWidget,
    PageHeader,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
    SpinBox,
    TabWidget,
)


class PdfToolkitPage(BasePage):
    page_id = "pdf_toolkit"
    page_title = "PDF 工具"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "PDF 工具",
                "合并 / 拆分 / 按页提取。只处理 PDF 文件；多图合成请用「文档合成器」。",
            )
        )

        self._tabs = TabWidget()
        self._tabs.addTab(self._build_merge_tab(), "合并")
        self._tabs.addTab(self._build_split_tab(), "拆分")
        self._tabs.addTab(self._build_extract_tab(), "按页提取")
        scroll.add_widget(self._tabs)

        log_box = FormSection("结果")
        self._log = ReadOnlyPlainTextEdit()
        self._log.setMinimumHeight(120)
        log_box.add_widget(self._log)
        scroll.add_widget(log_box)
        scroll.add_stretch(1)
        self.apply_page_focus_policy()

    def primary_focus_widget(self) -> QWidget | None:
        idx = self._tabs.currentIndex()
        if idx == 0:
            return self._merge_list
        if idx == 1:
            return self._split_path
        return self._extract_pages

    # —— 合并 ——
    def _build_merge_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        box = FormSection("PDF 列表（可拖拽调序）")
        self._merge_list = ListWidget()
        self._merge_list.setMinimumHeight(180)
        self._merge_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._merge_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        box.add_widget(self._merge_list)
        self._merge_summary = HintLabel("合计 0 页 · 0 个文件")
        box.add_widget(self._merge_summary)

        row = QHBoxLayout()
        btn_add = SecondaryButton("添加 PDF…")
        btn_add.clicked.connect(self._merge_add)
        row.addWidget(btn_add)
        btn_up = SecondaryButton("上移")
        btn_up.clicked.connect(lambda: self._move_item(-1))
        row.addWidget(btn_up)
        btn_down = SecondaryButton("下移")
        btn_down.clicked.connect(lambda: self._move_item(1))
        row.addWidget(btn_down)
        btn_rm = SecondaryButton("移除")
        btn_rm.clicked.connect(self._merge_remove)
        row.addWidget(btn_rm)
        row.addStretch(1)
        box.add_layout(row)
        lay.addWidget(box)

        actions = QHBoxLayout()
        btn_go = PrimaryButton("合并")
        btn_go.clicked.connect(self._on_merge)
        actions.addWidget(btn_go)
        actions.addStretch(1)
        lay.addLayout(actions)
        lay.addStretch(1)
        return w

    def _merge_add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择 PDF", "", "PDF (*.pdf)"
        )
        for path in paths:
            pages, err = inspect_pdf(path)
            item = QListWidgetItem()
            if err:
                item.setText(f"{Path(path).name}  —  无法使用：{err}")
                item.setData(Qt.ItemDataRole.UserRole, {"path": path, "pages": 0, "error": err})
                item.setForeground(Qt.GlobalColor.red)
            else:
                item.setText(f"{Path(path).name}  —  {pages} 页")
                item.setData(Qt.ItemDataRole.UserRole, {"path": path, "pages": pages, "error": None})
            self._merge_list.addItem(item)
        self._refresh_merge_summary()

    def _merge_remove(self) -> None:
        for item in self._merge_list.selectedItems():
            row = self._merge_list.row(item)
            self._merge_list.takeItem(row)
        self._refresh_merge_summary()

    def _move_item(self, delta: int) -> None:
        row = self._merge_list.currentRow()
        if row < 0:
            return
        new_row = row + delta
        if new_row < 0 or new_row >= self._merge_list.count():
            return
        item = self._merge_list.takeItem(row)
        self._merge_list.insertItem(new_row, item)
        self._merge_list.setCurrentRow(new_row)
        self._refresh_merge_summary()

    def _merge_entries(self) -> list[dict]:
        entries: list[dict] = []
        for i in range(self._merge_list.count()):
            data = self._merge_list.item(i).data(Qt.ItemDataRole.UserRole) or {}
            entries.append(data)
        return entries

    def _refresh_merge_summary(self) -> None:
        entries = self._merge_entries()
        ok = [e for e in entries if not e.get("error")]
        bad = [e for e in entries if e.get("error")]
        pages = sum(int(e.get("pages") or 0) for e in ok)
        msg = f"合计 {pages} 页 · {len(ok)} 个可用"
        if bad:
            msg += f" · {len(bad)} 个不可用（将跳过并点名）"
        self._merge_summary.setText(msg)

    def _on_merge(self) -> None:
        entries = self._merge_entries()
        if not entries:
            show_warning(self, "请先添加 PDF 文件。")
            return
        usable = [e["path"] for e in entries if not e.get("error")]
        if not usable:
            show_warning(self, "没有可合并的有效 PDF（请查看红色项原因）。")
            return

        def _run() -> None:
            out_dir = module_output_dir(self.page_id, create=True)
            out = Path(out_dir) / f"merged_{default_stamp()}.pdf"
            result = merge_pdfs(usable, out)
            # 把列表里预先标红的也并入 issues 展示
            for e in entries:
                if e.get("error"):
                    from modules.pdf_toolkit.pdf_service import FileIssue

                    result.issues.append(FileIssue(e["path"], str(e["error"])))
            self._log.setPlainText(result.summary)
            if result.ok_paths:
                self.report_status(
                    f"合并完成 · {result.total_pages} 页",
                    level=StatusLevel.SUCCESS if not result.issues else StatusLevel.WARNING,
                )
                show_saved(self, result.summary.split("\n", 1)[0], result.ok_paths[0])
            else:
                self.report_status("合并失败", level=StatusLevel.ERROR)
                show_warning(self, result.summary)

        self.run_safe(_run, title="PDF 合并失败")

    # —— 拆分 ——
    def _build_split_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        box = FormSection("源 PDF")
        row = QHBoxLayout()
        self._split_path = LineEdit()
        self._split_path.setPlaceholderText("选择要拆分的 PDF…")
        row.addWidget(self._split_path, 1)
        btn = SecondaryButton("浏览…")
        btn.clicked.connect(self._browse_split)
        row.addWidget(btn)
        box.add_layout(row)
        self._split_info = HintLabel("—")
        box.add_widget(self._split_info)

        opt = QHBoxLayout()
        opt.addWidget(HintLabel("每份页数"))
        self._split_n = SpinBox()
        self._split_n.setRange(1, 9999)
        self._split_n.setValue(1)
        opt.addWidget(self._split_n)
        opt.addStretch(1)
        box.add_layout(opt)
        lay.addWidget(box)

        actions = QHBoxLayout()
        btn_go = PrimaryButton("拆分")
        btn_go.clicked.connect(self._on_split)
        actions.addWidget(btn_go)
        actions.addStretch(1)
        lay.addLayout(actions)
        lay.addStretch(1)
        return w

    def _browse_split(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 PDF", "", "PDF (*.pdf)")
        if not path:
            return
        self._split_path.setText(path)
        pages, err = inspect_pdf(path)
        if err:
            self._split_info.setText(f"无法使用：{err}")
        else:
            self._split_info.setText(f"{pages} 页")

    def _on_split(self) -> None:
        path = self._split_path.text().strip()
        if not path:
            show_warning(self, "请先选择要拆分的 PDF。")
            return
        pages, err = inspect_pdf(path)
        if err:
            show_warning(self, f"{Path(path).name}: {err}")
            return

        def _run() -> None:
            out_dir = Path(module_output_dir(self.page_id, create=True)) / f"split_{default_stamp()}"
            result = split_pdf(path, out_dir, pages_per_file=self._split_n.value())
            self._log.setPlainText(result.summary)
            if result.ok_paths:
                self.report_status(
                    f"拆分完成 · {len(result.ok_paths)} 个文件",
                    level=StatusLevel.SUCCESS,
                )
                show_saved(self, result.summary.split("\n", 1)[0], result.ok_paths[0])
            else:
                self.report_status("拆分失败", level=StatusLevel.ERROR)
                show_warning(self, result.summary)

        self.run_safe(_run, title="PDF 拆分失败")

    # —— 按页提取 ——
    def _build_extract_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        box = FormSection("源 PDF 与页码")
        row = QHBoxLayout()
        self._extract_path = LineEdit()
        self._extract_path.setPlaceholderText("选择 PDF…")
        row.addWidget(self._extract_path, 1)
        btn = SecondaryButton("浏览…")
        btn.clicked.connect(self._browse_extract)
        row.addWidget(btn)
        box.add_layout(row)
        self._extract_info = HintLabel("—")
        box.add_widget(self._extract_info)
        box.add_widget(HintLabel("页码（1 起，支持 1,3,5-7）"))
        self._extract_pages = LineEdit()
        self._extract_pages.setPlaceholderText("例如 1,3,5-7")
        box.add_widget(self._extract_pages)
        lay.addWidget(box)

        actions = QHBoxLayout()
        btn_go = PrimaryButton("提取")
        btn_go.clicked.connect(self._on_extract)
        actions.addWidget(btn_go)
        actions.addStretch(1)
        lay.addLayout(actions)
        lay.addStretch(1)
        return w

    def _browse_extract(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 PDF", "", "PDF (*.pdf)")
        if not path:
            return
        self._extract_path.setText(path)
        pages, err = inspect_pdf(path)
        if err:
            self._extract_info.setText(f"无法使用：{err}")
        else:
            self._extract_info.setText(f"{pages} 页")

    def _on_extract(self) -> None:
        path = self._extract_path.text().strip()
        if not path:
            show_warning(self, "请先选择 PDF。")
            return
        nums = parse_page_spec(self._extract_pages.text())
        if not nums:
            show_warning(self, "请输入有效页码，例如 1,3,5-7。")
            return
        _, err = inspect_pdf(path)
        if err:
            show_warning(self, f"{Path(path).name}: {err}")
            return

        def _run() -> None:
            out_dir = module_output_dir(self.page_id, create=True)
            out = Path(out_dir) / f"extract_{default_stamp()}.pdf"
            result = extract_pages(path, out, nums)
            self._log.setPlainText(result.summary)
            if result.ok_paths:
                self.report_status(
                    f"提取完成 · {result.total_pages} 页",
                    level=StatusLevel.SUCCESS if not result.issues else StatusLevel.WARNING,
                )
                show_saved(self, result.summary.split("\n", 1)[0], result.ok_paths[0])
            else:
                self.report_status("提取失败", level=StatusLevel.ERROR)
                show_warning(self, result.summary)

        self.run_safe(_run, title="PDF 提取失败")

    def on_enter(self) -> None:
        self.report_status("PDF 工具 · 合并 / 拆分 / 抽页（仅 PDF）")
