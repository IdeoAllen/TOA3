# -*- coding: utf-8 -*-
"""培训交付看板：班级上下文 + 开班→交付串链（高级付费锚点）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from core.user_messages import show_warning
from services.class_session_handoff import ClassSession, load_session, save_session
from widgets import (
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PlainTextEdit,
    PrimaryButton,
    ScrollPage,
    SecondaryButton,
    SemanticLabel,
    ToolLaunchCard,
)

# 环节：module_id 为空表示本页动作（打开文档等）
_STAGES: list[dict[str, str]] = [
    {
        "id": "mkdir",
        "title": "批量建夹",
        "subtitle": "粘贴名单 → 建班级目录",
        "module_id": "directory_generator",
        "icon": "directory_generator",
    },
    {
        "id": "table_card",
        "title": "桌卡生成",
        "subtitle": "学员信息 → 台卡 PPT",
        "module_id": "table_card_generator",
        "icon": "table_card_generator",
    },
    {
        "id": "watermark",
        "title": "水印照片",
        "subtitle": "班级目录按规则加水印",
        "module_id": "watermark_photo_generator",
        "icon": "watermark_photo",
    },
    {
        "id": "inspect",
        "title": "目录透视",
        "subtitle": "结构自查 · 空目录/命名",
        "module_id": "directory_inspector",
        "icon": "directory_inspector",
    },
    {
        "id": "report",
        "title": "交付报告",
        "subtitle": "Word 大纲贴图 + Excel 统计",
        "module_id": "deliverable_directory_check",
        "icon": "deliverable_directory_check",
    },
    {
        "id": "pack",
        "title": "打包归档",
        "subtitle": "规范命名 zip",
        "module_id": "file_packager",
        "icon": "package",
    },
]


class TrainingDeliveryBoardPage(BasePage):
    page_id = "training_delivery_board"
    page_title = "培训交付看板"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._suppress = False
        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        outer.setSpacing(10)

        outer.addWidget(
            PageHeader(
                "培训交付看板",
                "绑定班级一次，开班→交付串本机工具；腾讯文档可开可粘，不依赖 DMS。",
            )
        )

        scroll = ScrollPage()
        outer.addWidget(scroll, 1)

        bind = FormSection("班级上下文")
        self._class_name = LineEdit()
        self._class_name.setPlaceholderText("班级名称…")
        self._class_name.textChanged.connect(self._on_field_changed)
        bind.add_widget(self._class_name)

        path_row = QHBoxLayout()
        self._root = LineEdit()
        self._root.setPlaceholderText("本机班级根目录…")
        self._root.textChanged.connect(self._on_field_changed)
        path_row.addWidget(self._root, 1)
        btn_browse = SecondaryButton("浏览…")
        btn_browse.clicked.connect(self._browse_root)
        path_row.addWidget(btn_browse)
        bind.add_layout(path_row)

        doc_row = QHBoxLayout()
        self._doc_url = LineEdit()
        self._doc_url.setPlaceholderText("腾讯文档链接（可选）…")
        self._doc_url.textChanged.connect(self._on_field_changed)
        doc_row.addWidget(self._doc_url, 1)
        btn_open_doc = SecondaryButton("打开文档")
        btn_open_doc.clicked.connect(self._open_doc)
        doc_row.addWidget(btn_open_doc)
        bind.add_layout(doc_row)

        bind.add_widget(HintLabel("无 OAuth 时：从文档复制花名册粘到下方即可开跑，不堵主路径。"))
        self._roster = PlainTextEdit()
        self._roster.setPlaceholderText("花名册 / 文件夹名单（每行一个，可从腾讯文档或 Excel 粘贴）…")
        self._roster.setMinimumHeight(120)
        self._roster.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.MinimumExpanding,
        )
        self._roster.textChanged.connect(self._on_field_changed)
        bind.add_widget(self._roster, stretch=1)

        actions = QHBoxLayout()
        btn_bind = PrimaryButton("绑定班级")
        btn_bind.clicked.connect(self._bind_class)
        actions.addWidget(btn_bind)
        btn_copy = SecondaryButton("复制根目录")
        btn_copy.clicked.connect(self._copy_root)
        actions.addWidget(btn_copy)
        btn_clear = SecondaryButton("清除会话")
        btn_clear.clicked.connect(self._clear_session)
        actions.addWidget(btn_clear)
        actions.addStretch(1)
        bind.add_layout(actions)

        self._ctx_badge = SemanticLabel("尚未绑定班级", kind="info", compact=True)
        bind.add_widget(self._ctx_badge)
        scroll.add_widget(bind)

        chain = FormSection("开班 → 交付（点环节即办事，带上班级上下文）")
        grid = QGridLayout()
        grid.setSpacing(10)
        self._stage_cards: dict[str, ToolLaunchCard] = {}
        for i, stage in enumerate(_STAGES):
            card = ToolLaunchCard(
                stage["title"],
                subtitle=stage["subtitle"],
                icon=stage.get("icon") or "file-text",
                status="mvp",
            )
            mid = stage["module_id"]
            sid = stage["id"]
            card.activated.connect(
                lambda _=False, module_id=mid, stage_id=sid: self._launch(module_id, stage_id)
            )
            self._stage_cards[sid] = card
            grid.addWidget(card, i // 3, i % 3)
        wrap = QWidget()
        wrap.setLayout(grid)
        chain.add_widget(wrap)
        chain.add_widget(
            HintLabel("不依赖 DMS 在线；需要完善系统时另购 DMS，非本页前提。")
        )
        scroll.add_widget(chain)

        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        return self._class_name

    def on_enter(self) -> None:
        self._load_into_form()
        self.report_status("培训交付看板")
        self.schedule_primary_focus()

    def _on_field_changed(self, *_args) -> None:
        if self._suppress:
            return
        # 自动草稿：不强制完整绑定也能改字段
        session = self._form_session()
        if session.class_name or session.root_path or session.doc_url or session.roster_text.strip():
            prev = load_session()
            session.stage_done = dict(prev.stage_done)
            save_session(session)
            self._refresh_badge(session)

    def _form_session(self) -> ClassSession:
        return ClassSession(
            class_name=self._class_name.text().strip(),
            root_path=self._root.text().strip(),
            doc_url=self._doc_url.text().strip(),
            roster_text=self._roster.toPlainText(),
            stage_done=dict(load_session().stage_done),
        )

    def _load_into_form(self) -> None:
        self._suppress = True
        try:
            session = load_session()
            self._class_name.setText(session.class_name)
            self._root.setText(session.root_path)
            self._doc_url.setText(session.doc_url)
            self._roster.setPlainText(session.roster_text)
            self._refresh_badge(session)
            self._refresh_stage_dots(session)
        finally:
            self._suppress = False

    def _refresh_badge(self, session: ClassSession) -> None:
        if session.class_name and session.root_path:
            self._ctx_badge.setText(
                f"已绑定 · {session.class_name} · {session.root_path}"
            )
            self._ctx_badge.setProperty("class", "semantic-success")
        elif session.class_name or session.root_path:
            self._ctx_badge.setText("草稿未齐 · 请填班级名与根目录后点「绑定班级」")
            self._ctx_badge.setProperty("class", "semantic-warning")
        else:
            self._ctx_badge.setText("尚未绑定班级")
            self._ctx_badge.setProperty("class", "semantic-info")
        self._ctx_badge.setProperty("compact", "true")
        st = self._ctx_badge.style()
        if st is not None:
            st.unpolish(self._ctx_badge)
            st.polish(self._ctx_badge)

    def _refresh_stage_dots(self, session: ClassSession) -> None:
        for stage in _STAGES:
            card = self._stage_cards.get(stage["id"])
            if card is None:
                continue
            done = bool(session.stage_done.get(stage["id"]))
            # ToolLaunchCard 无公开 set_status；用 tooltip 提示
            tip = "本班已标记完成" if done else stage["subtitle"]
            card.setToolTip(tip)

    def _browse_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择班级根目录")
        if path:
            self._root.setText(path)

    def _bind_class(self) -> None:
        session = self._form_session()
        if not session.class_name:
            show_warning(self, "请填写班级名称")
            self.report_status("缺少班级名称", level=StatusLevel.WARNING)
            return
        if not session.root_path:
            show_warning(self, "请选择或粘贴本机班级根目录")
            self.report_status("缺少根目录", level=StatusLevel.WARNING)
            return
        root = Path(session.root_path)
        if not root.is_dir():
            show_warning(self, f"根目录不存在：{session.root_path}")
            self.report_status("根目录无效", level=StatusLevel.WARNING)
            return
        session.root_path = str(root.resolve())
        save_session(session)
        self._refresh_badge(session)
        self._refresh_stage_dots(session)
        self.report_status(
            f"已绑定班级「{session.class_name}」",
            level=StatusLevel.SUCCESS,
        )

    def _copy_root(self) -> None:
        text = self._root.text().strip()
        if not text:
            show_warning(self, "根目录为空")
            return
        QGuiApplication.clipboard().setText(text)
        self.report_status("已复制根目录", level=StatusLevel.SUCCESS)

    def _clear_session(self) -> None:
        from services.class_session_handoff import clear_session

        clear_session()
        self._suppress = True
        try:
            self._class_name.clear()
            self._root.clear()
            self._doc_url.clear()
            self._roster.clear()
        finally:
            self._suppress = False
        self._refresh_badge(ClassSession())
        self._refresh_stage_dots(ClassSession())
        self.report_status("已清除班级会话")

    def _open_doc(self) -> None:
        url = self._doc_url.text().strip()
        if not url:
            show_warning(self, "请先填写腾讯文档链接；或直接粘贴花名册到下方，无需 OAuth。")
            self.report_status("无文档链接 · 可粘贴花名册", level=StatusLevel.INFO)
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            show_warning(self, "文档链接需以 http:// 或 https:// 开头")
            return
        ok = QDesktopServices.openUrl(QUrl(url))
        if ok:
            self.report_status("已在浏览器打开腾讯文档", level=StatusLevel.SUCCESS)
        else:
            show_warning(self, "无法打开链接，请检查地址或手动粘贴花名册继续。")
            self.report_status("打开文档失败 · 可粘贴继续", level=StatusLevel.WARNING)

    def _launch(self, module_id: str, stage_id: str) -> None:
        session = self._form_session()
        prev = load_session()
        session.stage_done = dict(prev.stage_done)
        # 跳转前落盘，保证目标页能读到
        if session.class_name or session.root_path or session.roster_text.strip():
            save_session(session)

        win = self.window()
        if win is None or not hasattr(win, "navigate"):
            show_warning(self, "无法切换模块（壳未就绪）")
            return
        win.navigate(module_id)
        pages = getattr(win, "_pages", {}) or {}
        page = pages.get(module_id)
        if page is not None and hasattr(page, "apply_class_context"):
            try:
                page.apply_class_context(load_session())
            except Exception:
                pass
        # 标记「已进入」该环（完成态由用户回看板或后续增强）
        session = load_session()
        session.stage_done[stage_id] = True
        save_session(session)
        self.report_status(f"已打开 · {_title_for(stage_id)}（已带班级上下文）")


def _title_for(stage_id: str) -> str:
    for s in _STAGES:
        if s["id"] == stage_id:
            return s["title"]
    return stage_id
