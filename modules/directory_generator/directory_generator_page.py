# -*- coding: utf-8 -*-
"""批量文件夹生成。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QSizePolicy,
    QSplitter,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from core.user_messages import show_saved, show_warning
from modules.directory_generator.directory_generator_service import (
    DIRECTORY_TEMPLATES,
    create_directories,
    parse_names,
)
from widgets import (
    ComboBox,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PlainTextEdit,
    PrimaryButton,
    SecondaryButton,
    SemanticLabel,
    TreeWidget,
)

_TEMPLATES: dict[str, str] = {k: v[1] for k, v in DIRECTORY_TEMPLATES.items()}


class DirectoryGeneratorPage(BasePage):
    page_id = "directory_generator"
    page_title = "批量文件夹生成"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        outer.setSpacing(10)

        outer.addWidget(
            PageHeader(
                "批量文件夹生成",
                "左侧编辑名单，右侧实时预览结构；创建时已存在的目录会跳过。",
            )
        )

        # —— 顶栏：父目录 + 模板 + 操作 ——
        bar = FormSection("目标与操作")
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self._parent = LineEdit()
        self._parent.setPlaceholderText("选择或粘贴父目录路径…")
        self._parent.textChanged.connect(self._preview)
        path_row.addWidget(self._parent, 1)
        btn_browse = SecondaryButton("浏览…")
        btn_browse.clicked.connect(self._browse)
        path_row.addWidget(btn_browse)
        bar.add_layout(path_row)

        ops = QHBoxLayout()
        ops.setSpacing(8)
        ops.addWidget(HintLabel("模板"))
        self._tpl = ComboBox()
        self._tpl.setMinimumWidth(200)
        self._tpl.setMinimumContentsLength(12)
        for key, (label, _body) in DIRECTORY_TEMPLATES.items():
            self._tpl.addItem(label, key)
        self._tpl.currentIndexChanged.connect(self._apply_template)
        ops.addWidget(self._tpl, 1)
        self._count = SemanticLabel("0 项", kind="info", compact=True)
        ops.addWidget(self._count)
        ops.addStretch(1)
        btn_go = PrimaryButton("创建目录")
        btn_go.clicked.connect(self._on_create)
        ops.addWidget(btn_go)
        btn_clear = SecondaryButton("清空")
        btn_clear.clicked.connect(self._on_clear)
        ops.addWidget(btn_clear)
        btn_copy = SecondaryButton("复制预览")
        btn_copy.setToolTip("复制右侧结构文本到剪贴板")
        btn_copy.clicked.connect(self._copy_preview)
        ops.addWidget(btn_copy)
        bar.add_layout(ops)
        outer.addWidget(bar)

        # —— 左右：名单 | 预览树 ——
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)

        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 4, 0)
        left_lay.setSpacing(8)
        names_box = FormSection("文件夹名单")
        self._names = PlainTextEdit()
        self._names.setPlaceholderText("每行一个文件夹名，可从 Excel 粘贴…\n支持缩进表示子目录（如有模板）。")
        self._names.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._names.setMinimumHeight(220)
        self._names.textChanged.connect(self._preview)
        names_box.add_widget(self._names, stretch=1)
        names_box.add_widget(HintLabel("改名单即刷新右侧预览；空行自动忽略。"))
        names_box.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        left_lay.addWidget(names_box, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(4, 0, 0, 0)
        right_lay.setSpacing(8)
        preview_box = FormSection("结构预览")
        self._result_badge = SemanticLabel("尚未创建", kind="info", compact=True)
        preview_box.add_widget(self._result_badge)
        self._tree = TreeWidget()
        self._tree.setMinimumHeight(220)
        self._tree.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        preview_box.add_widget(self._tree, stretch=1)
        preview_box.add_widget(HintLabel("创建后同名目录会跳过，不会覆盖（可续跑）。"))
        preview_box.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        right_lay.addWidget(preview_box, 1)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([520, 520])
        outer.addWidget(splitter, 1)

        self.apply_page_focus_policy()
        self._preview()

    def primary_focus_widget(self):
        return self._names

    def _apply_template(self) -> None:
        key = str(self._tpl.currentData() or "blank")
        text = _TEMPLATES.get(key, "")
        if text:
            self._names.setPlainText(text)
        self._preview()

    def _preview(self) -> None:
        parent = self._parent.text().strip() or "（未选父目录）"
        names = parse_names(self._names.toPlainText())
        n = len(names)
        self._count.setText(f"{n} 项")
        self._count.setProperty("class", f"semantic-{'success' if n else 'info'}")
        self._count.setProperty("compact", "true")
        st = self._count.style()
        if st is not None:
            st.unpolish(self._count)
            st.polish(self._count)

        self._tree.clear()
        root = QTreeWidgetItem([parent])
        root.setExpanded(True)
        self._tree.addTopLevelItem(root)
        if not names:
            empty = QTreeWidgetItem(["（名单为空）"])
            root.addChild(empty)
            return
        for name in names:
            root.addChild(QTreeWidgetItem([name]))
        root.setExpanded(True)

    def _copy_preview(self) -> None:
        parent = self._parent.text().strip() or "（未选父目录）"
        names = parse_names(self._names.toPlainText())
        if not names:
            show_warning(self, "名单为空，没有可复制的内容。")
            return
        lines = [f"{parent}/"] + [f"  └ {n}/" for n in names]
        QGuiApplication.clipboard().setText("\n".join(lines))
        self.report_status(f"已复制 {len(names)} 项预览", level=StatusLevel.SUCCESS)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择父目录")
        if path:
            self._parent.setText(path)
            self._preview()

    def _on_clear(self) -> None:
        self._names.clear()
        self._result_badge.setText("尚未创建")
        self._result_badge.setProperty("class", "semantic-info")
        self._result_badge.setProperty("compact", "true")
        st = self._result_badge.style()
        if st is not None:
            st.unpolish(self._result_badge)
            st.polish(self._result_badge)
        self._preview()

    def _on_create(self) -> None:
        parent = self._parent.text().strip()
        names = parse_names(self._names.toPlainText())
        if not parent:
            show_warning(self, "请先选择目标父目录。")
            return
        if not names:
            show_warning(self, "请至少输入一个文件夹名称。")
            return

        def _run() -> None:
            result = create_directories(parent, names)
            created = len(result.created)
            skipped = len(getattr(result, "skipped", []) or [])
            errors = len(result.errors)
            if errors:
                kind = "warning"
                badge = f"完成 · 新建 {created} · 跳过 {skipped} · 失败 {errors}"
            else:
                kind = "success"
                badge = f"完成 · 新建 {created} · 跳过 {skipped}"
            self._result_badge.setText(badge)
            self._result_badge.setProperty("class", f"semantic-{kind}")
            self._result_badge.setProperty("compact", "true")
            st = self._result_badge.style()
            if st is not None:
                st.unpolish(self._result_badge)
                st.polish(self._result_badge)
            self._preview()
            # 在预览树底部追加「本次结果」折叠节点
            root = self._tree.topLevelItem(0)
            if root is not None:
                result_node = QTreeWidgetItem(["本次结果"])
                for line in result.summary.splitlines()[1:]:
                    result_node.addChild(QTreeWidgetItem([line.strip() or line]))
                if not result_node.childCount():
                    result_node.addChild(QTreeWidgetItem([result.summary.split("\n", 1)[0]]))
                root.addChild(result_node)
                result_node.setExpanded(True)
            self.report_status(
                f"已创建 {created} 个目录",
                level=StatusLevel.SUCCESS if not result.errors else StatusLevel.WARNING,
            )
            show_saved(self, result.summary.split("\n", 1)[0], parent)

        self.run_safe(_run, title="创建目录失败")

    def on_enter(self) -> None:
        self._preview()
        self.report_status("批量文件夹生成")
        self.schedule_primary_focus()
