# -*- coding: utf-8 -*-
"""系统 · 扩展：自定义插件 / 插件市场 双页签（控件库）。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.base_dialog import BaseDialog
from core.base_page import BasePage
from core.user_messages import ask_confirm, show_error, show_success, show_warning
from services.extension_lifecycle import (
    LIFE_READY,
    create_and_start_development,
    enrich_managed_rows,
    mark_development_done,
    start_development,
    uninstall_extension,
)
from services.extension_pack_io import export_extension_zip, import_extension_zip
from services.icon_registry import icon_pixmap
from services.os_open import open_in_file_manager
from services.plugin_loader import audit_plugin_root
from services.plugin_registry import register_plugin, set_plugin_show
from services.plugin_sandbox import ensure_extensions_home
from services.notify_bus import request_nav_rebuild
from services.soft_asset_client import (
    download_and_install_plugin,
    list_public_plugins,
    submit_extension_to_cloud,
)
from widgets import (
    ComboBox,
    DialogButtonRow,
    FormSection,
    GridBox,
    HintLabel,
    LineEdit,
    MenuButton,
    PlainTextEdit,
    PrimaryButton,
    ScrollPage,
    SecondaryButton,
    SemanticLabel,
    TabWidget,
)


def _primary_fg() -> str:
    try:
        from app.app_state import AppState

        return str((AppState.get().palette or {}).get("primary") or "#2563EB")
    except Exception:
        return "#2563EB"


class _CreateExtensionDialog(BaseDialog):
    """新增扩展：名称 + 需求，确认后创建并投喂智能体。"""

    dialog_kind = "large"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("新增扩展")

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(
            HintLabel("写清名称与需求，确认后创建目录并投喂智能体（需已配置 Harness Key）。")
        )

        lay.addWidget(HintLabel("名称"))
        self._name = LineEdit()
        self._name.setPlaceholderText("侧栏显示名，如：备品管理")
        self._name.setMinimumHeight(36)
        lay.addWidget(self._name)

        lay.addWidget(HintLabel("需求（必填）"))
        self._desc = PlainTextEdit()
        self._desc.setPlaceholderText(
            "场景 · 痛点 · 作用 · 主路径（打开后先做什么、得到什么）"
        )
        self._desc.setMinimumHeight(140)
        lay.addWidget(self._desc)

        lay.addWidget(HintLabel("界面类型"))
        self._surface = ComboBox()
        self._surface.addItem("表单页（Qt 控件库 · 默认）", "qt")
        self._surface.addItem("网页界面（HTML/JS · 游戏/可视化）", "webview")
        lay.addWidget(self._surface)

        buttons = DialogButtonRow()
        buttons.add_secondary("取消", self.reject)
        buttons.add_primary("创建并去开发", self._on_ok)
        lay.addWidget(buttons)

    def _on_ok(self) -> None:
        name = self._name.text().strip()
        desc = self._desc.toPlainText().strip()
        if not name:
            show_warning(self, "请填写名称")
            self._name.setFocus()
            return
        if len(desc) < 8:
            show_warning(self, "请写清需求：做什么、给谁用（至少数十字）。")
            self._desc.setFocus()
            return
        self.accept()

    def values(self) -> tuple[str, str, str]:
        return (
            self._name.text().strip(),
            self._desc.toPlainText().strip(),
            str(self._surface.currentData() or "qt"),
        )


class _MarketPluginCard(QFrame):
    """插件市场卡片：文案区 + 右侧下载按钮（跟 ToolLaunchCard 主题）。"""

    download_clicked = Signal(dict)

    def __init__(self, asset: dict, parent=None) -> None:
        super().__init__(parent)
        self._asset = asset
        self.setObjectName("ToolLaunchCard")
        self.setProperty("class", "tool-card")
        self.setMinimumHeight(96)
        self.setMinimumWidth(280)

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 12, 12)
        root.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setObjectName("ToolCardIcon")
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(icon_pixmap("package", color=_primary_fg(), size=28, parent=self))
        root.addWidget(icon_lbl)

        text = QVBoxLayout()
        text.setSpacing(2)
        badge = "【推荐】" if asset.get("recommended") else ""
        title = QLabel(
            f"{badge}{str(asset.get('name') or asset.get('plugin_id') or '插件')}"
        )
        title.setObjectName("ToolCardTitle")
        title.setProperty("class", "section-title")
        title.setWordWrap(True)
        text.addWidget(title)

        caps = asset.get("capabilities") or []
        cap_s = (
            " · ".join(str(c) for c in caps)
            if isinstance(caps, list)
            else str(caps or "l1")
        )
        desc = str(asset.get("description") or "").strip() or "办公扩展"
        if len(desc) > 42:
            desc = desc[:42] + "…"
        author = str(asset.get("author") or "匿名")
        ver = str(asset.get("version") or "")
        sub = QLabel(f"{desc}\n{author} · v{ver} · {cap_s or 'l1'}")
        sub.setObjectName("ToolCardSub")
        sub.setProperty("class", "hint")
        sub.setWordWrap(True)
        text.addWidget(sub)

        tag = QLabel("推荐 · 无偿" if asset.get("recommended") else "无偿流通")
        tag.setObjectName("ToolCardShortcut")
        tag.setProperty("class", "hint")
        text.addWidget(tag)
        text.addStretch(1)
        root.addLayout(text, 1)

        btn = PrimaryButton("下载")
        btn.setMinimumWidth(72)
        btn.setMinimumHeight(36)
        btn.setToolTip("下载并安装到本机「自定义插件」")
        btn.clicked.connect(lambda: self.download_clicked.emit(self._asset))
        root.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hover", "true")
        self.style().unpolish(self)
        self.style().polish(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hover", "false")
        self.style().unpolish(self)
        self.style().polish(self)
        super().leaveEvent(event)


class _MinePluginCard(QFrame):
    """本机扩展卡片：主操作一眼可见，其余收进「更多」。"""

    primary_clicked = Signal(dict)
    more_action = Signal(str, dict)
    selected = Signal(dict)

    def __init__(self, row: dict, parent=None) -> None:
        super().__init__(parent)
        self._row = row
        life = str(row.get("lifecycle") or "")
        ready = life == LIFE_READY
        self.setObjectName("ToolLaunchCard")
        self.setProperty("class", "tool-card")
        self.setMinimumHeight(96)
        self.setMinimumWidth(280)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 12, 12)
        root.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setObjectName("ToolCardIcon")
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(
            icon_pixmap(
                "package" if ready else "harness_agent",
                color=_primary_fg(),
                size=28,
                parent=self,
            )
        )
        root.addWidget(icon_lbl)

        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(str(row.get("name") or row.get("id") or "扩展"))
        title.setObjectName("ToolCardTitle")
        title.setProperty("class", "section-title")
        title.setWordWrap(True)
        text.addWidget(title)

        status = str(row.get("lifecycle_label") or "")
        sub = QLabel(status or "本机扩展")
        sub.setObjectName("ToolCardSub")
        sub.setProperty("class", "hint")
        sub.setWordWrap(True)
        text.addWidget(sub)

        tag = QLabel("已上架业务" if ready else "开发中 · 完成后上架业务")
        tag.setObjectName("ToolCardShortcut")
        tag.setProperty("class", "hint")
        text.addWidget(tag)
        text.addStretch(1)
        root.addLayout(text, 1)

        actions = QVBoxLayout()
        actions.setSpacing(6)
        primary_text = "打开" if ready else "开发完成"
        primary_tip = (
            "打开到顶栏「业务」"
            if ready
            else "体检通过后上架到「业务」侧栏"
        )
        btn_primary = PrimaryButton(primary_text)
        btn_primary.setMinimumWidth(88)
        btn_primary.setMinimumHeight(36)
        btn_primary.setToolTip(primary_tip)
        btn_primary.clicked.connect(lambda: self.primary_clicked.emit(self._row))
        actions.addWidget(btn_primary)

        btn_more = MenuButton("更多")
        btn_more.setMinimumWidth(88)
        btn_more.setMinimumHeight(32)
        btn_more.setToolTip("回到开发、上传、导出、隐藏、移除等")
        menu = QMenu(btn_more)
        menu.addAction("回到开发").triggered.connect(
            lambda: self.more_action.emit("develop", self._row)
        )
        menu.addAction("上传社区").triggered.connect(
            lambda: self.more_action.emit("upload", self._row)
        )
        menu.addAction("导出包").triggered.connect(
            lambda: self.more_action.emit("export", self._row)
        )
        menu.addAction("打开文件夹").triggered.connect(
            lambda: self.more_action.emit("folder", self._row)
        )
        if ready:
            menu.addAction("从侧栏隐藏").triggered.connect(
                lambda: self.more_action.emit("hide", self._row)
            )
        menu.addSeparator()
        menu.addAction("移除").triggered.connect(
            lambda: self.more_action.emit("remove", self._row)
        )
        btn_more.setMenu(menu)
        actions.addWidget(btn_more)
        actions.addStretch(1)
        root.addLayout(actions)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self._row)
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hover", "true")
        self.style().unpolish(self)
        self.style().polish(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hover", "false")
        self.style().unpolish(self)
        self.style().polish(self)
        super().leaveEvent(event)


def _shell_of(widget):
    w = widget
    while w is not None and not hasattr(w, "navigate"):
        w = w.parent() if hasattr(w, "parent") else None
    return w


def _user_audit_fail(report) -> str:
    plain = ""
    if hasattr(report, "user_summary"):
        plain = str(report.user_summary() or "").strip()
    if not plain:
        plain = "扩展未通过安全检查。"
    return (
        f"{plain}\n\n"
        "请到智能体按本扩展目录内 AGENTS.md 修改后再试。\n"
        "不会影响官方功能与其它扩展。"
    )


class ExtensionsSection(QWidget):
    """双页签：自定义插件（本机开发）· 插件市场（社区无偿流通）。"""

    def __init__(self, page: BasePage, parent=None) -> None:
        super().__init__(parent)
        self._page = page
        self._selected_id = ""
        self._selected_root = ""
        self._selected_name = ""
        self._selected_life = ""
        self._rows: list[dict] = []
        self._community_rows: list[dict] = []
        self._selected_asset_id = 0
        self._selected_asset_name = ""

        ensure_extensions_home()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        self._tabs = TabWidget()
        self._tabs.addTab(self._build_create_tab(), "自定义插件")
        self._tabs.addTab(self._build_browse_tab(), "插件市场")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        outer.addWidget(self._tabs, 1)

        self._tip = HintLabel("")
        self._tip.setWordWrap(True)
        outer.addWidget(self._tip)

        self.reload()

    def _build_create_tab(self) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(
            SemanticLabel(
                "「新增」写需求 → 智能体开发 →「开发完成」上架业务；可导入包，随时移除。",
                kind="info",
            )
        )

        mine = FormSection("我的扩展")
        tools = QHBoxLayout()
        tools.addStretch(1)
        self._btn_add = PrimaryButton("新增")
        self._btn_add.setMinimumHeight(32)
        self._btn_add.setToolTip("填写名称与需求，创建并投喂智能体")
        self._btn_add.clicked.connect(self._on_create)
        tools.addWidget(self._btn_add)
        self._btn_import = SecondaryButton("导入包")
        self._btn_import.setMinimumHeight(32)
        self._btn_import.setToolTip("从本机 .toa-ext.zip 导入扩展")
        self._btn_import.clicked.connect(self._on_import)
        tools.addWidget(self._btn_import)
        mine.add_layout(tools)

        self._mine_empty = HintLabel("还没有扩展。点右上角「新增」开始，或「导入包」。")
        self._mine_empty.setWordWrap(True)
        mine.add_widget(self._mine_empty)

        self._mine_scroll = ScrollPage(padded=False)
        self._mine_scroll.setMinimumHeight(200)
        self._mine_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._mine_grid = GridBox(columns=2, spacing=12)
        self._mine_scroll.add_widget(self._mine_grid)
        self._mine_scroll.add_stretch(1)
        mine.add_widget(self._mine_scroll, 1)
        lay.addWidget(mine, 1)
        return host

    def _build_browse_tab(self) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(
            SemanticLabel(
                "社区无偿流通。下载后可在「自定义插件」继续开发或直接用。",
                kind="info",
            )
        )

        search = FormSection("市场检索")
        crow = QHBoxLayout()
        self._community_q = LineEdit()
        self._community_q.setPlaceholderText("名称 · 简介 · 作者")
        self._community_q.setMinimumHeight(36)
        self._community_q.returnPressed.connect(self._on_community_search)
        crow.addWidget(self._community_q, 1)
        btn_search = PrimaryButton("检索")
        btn_search.setMinimumHeight(36)
        btn_search.clicked.connect(self._on_community_search)
        crow.addWidget(btn_search)
        btn_refresh = SecondaryButton("刷新")
        btn_refresh.setMinimumHeight(36)
        btn_refresh.clicked.connect(self._on_community_search)
        crow.addWidget(btn_refresh)
        search.add_layout(crow)
        lay.addWidget(search)

        cards = FormSection("插件卡片")
        self._cards_empty = HintLabel(
            "暂无公示插件。本机扩展上传社区、审核通过后出现于此。"
        )
        self._cards_empty.setWordWrap(True)
        cards.add_widget(self._cards_empty)

        self._cards_scroll = ScrollPage(padded=False)
        self._cards_scroll.setMinimumHeight(240)
        self._cards_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._cards_grid = GridBox(columns=2, spacing=12)
        self._cards_scroll.add_widget(self._cards_grid)
        self._cards_scroll.add_stretch(1)
        cards.add_widget(self._cards_scroll, 1)
        lay.addWidget(cards, 1)
        return host

    def primary_focus_widget(self) -> QWidget | None:
        return self._btn_add

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            self._on_community_search()
        elif index == 0:
            self.reload()

    def _apply_selection(self, row: dict) -> None:
        self._selected_id = str(row.get("id") or "")
        self._selected_root = str(row.get("root") or "")
        self._selected_name = str(row.get("name") or self._selected_id)
        self._selected_life = str(row.get("lifecycle") or "")
        label = str(row.get("lifecycle_label") or "")
        if self._selected_name:
            self._tip.setText(f"已选「{self._selected_name}」· {label}")

    def _clear_selection(self) -> None:
        self._selected_id = ""
        self._selected_root = ""
        self._selected_name = ""
        self._selected_life = ""

    def _clear_mine_cards(self) -> None:
        lay = self._mine_scroll.content_layout
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._mine_grid = GridBox(columns=2, spacing=12)
        lay.addWidget(self._mine_grid)
        lay.addStretch(1)

    def reload(self) -> None:
        rows = enrich_managed_rows()
        self._rows = rows
        self._clear_mine_cards()
        self._clear_selection()

        if not rows:
            self._mine_empty.setVisible(True)
            self._mine_empty.setText("还没有扩展。点右上角「新增」开始，或「导入包」。")
        else:
            self._mine_empty.setVisible(False)
            for row in rows:
                card = _MinePluginCard(row)
                card.selected.connect(self._apply_selection)
                card.primary_clicked.connect(self._on_card_primary)
                card.more_action.connect(self._on_card_more)
                self._mine_grid.add_widget(card)

        n = len(rows)
        if self._tabs.currentIndex() == 0:
            self._tip.setText(
                f"共 {n} 个本机扩展。主按钮完成/打开；「更多」含上传与导出。"
                if n
                else "还没有扩展。点「新增」写需求并开发。"
            )

    def _on_card_primary(self, row: dict) -> None:
        self._apply_selection(row)
        life = str(row.get("lifecycle") or "")
        if life == LIFE_READY:
            self._on_open()
        else:
            self._on_done()

    def _on_card_more(self, action: str, row: dict) -> None:
        self._apply_selection(row)
        if action == "develop":
            self._on_develop()
        elif action == "upload":
            self._on_upload_cloud()
        elif action == "export":
            self._on_export()
        elif action == "folder":
            self._on_folder()
        elif action == "hide":
            self._on_hide()
        elif action == "remove":
            self._on_remove()

    def _on_create(self) -> None:
        dlg = _CreateExtensionDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, desc, surface = dlg.values()
        shell = _shell_of(self)
        if shell is None:
            show_error(self, "无法打开智能体")
            return
        try:
            created = create_and_start_development(
                shell,
                name=name,
                description=desc,
                surface=surface,
            )
            self.reload()
            for row in self._rows:
                if row.get("id") == created.plugin_id:
                    self._apply_selection(row)
                    break
            self._page.report_status(
                f"已创建「{created.name}」· 需求已投喂智能体，请在侧栏查看进度"
            )
        except Exception as exc:
            show_error(self, f"创建失败：{exc}")

    def _on_develop(self) -> None:
        if not self._selected_root:
            return
        shell = _shell_of(self)
        if shell is None:
            show_error(self, "无法打开智能体")
            return
        try:
            start_development(
                shell,
                plugin_id=self._selected_id,
                root=self._selected_root,
                name=self._selected_name,
                resume=True,
            )
            self.reload()
            self._page.report_status(
                f"已回到「{self._selected_name}」开发会话（未新建）"
            )
        except Exception as exc:
            show_error(self, str(exc))

    def _on_done(self) -> None:
        if not self._selected_id:
            return
        mid = self._selected_id
        name = self._selected_name
        root = self._selected_root
        try:
            if root:
                man, report = audit_plugin_root(root)
                if not report.ok or man is None:
                    show_error(self, _user_audit_fail(report))
                    return
            from services.extension_lifecycle import guard_report_for_plugin

            mark_development_done(mid)
            guard = guard_report_for_plugin(mid)
            self.reload()
            for row in self._rows:
                if row.get("id") == mid:
                    self._apply_selection(row)
                    break
            extra = ""
            if guard.findings:
                warns = [
                    f.message for f in guard.findings if f.level in ("warning", "info")
                ]
                if warns:
                    extra = "\n\n体检：\n- " + "\n- ".join(warns[:4])
            if ask_confirm(
                self,
                f"「{name}」已上架到「业务」。{extra}\n\n"
                "现在打开该功能？\n"
                "（也可稍后到顶栏「业务」打开。）",
                title="开发完成",
            ):
                self._on_open()
            else:
                show_success(self, f"「{name}」已可用。顶栏「业务」即可使用。")
        except Exception as exc:
            show_error(self, str(exc))

    def _on_open(self) -> None:
        if not self._selected_id:
            return
        if self._selected_life not in (LIFE_READY,):
            show_warning(
                self,
                "请先点「开发完成」。开发中的扩展不会出现在「业务」侧栏。",
            )
            return
        mid = self._selected_id
        name = self._selected_name or mid
        try:
            if self._selected_root:
                man, report = audit_plugin_root(self._selected_root)
                if not report.ok or man is None:
                    show_error(self, _user_audit_fail(report))
                    return
                register_plugin(man.root, show=True, status="mvp")
                request_nav_rebuild()
        except Exception as exc:
            show_error(self, f"无法打开。请重启后再试。（{exc}）")
            return
        shell = _shell_of(self)
        if shell is None:
            return
        try:
            if hasattr(shell, "select_domain"):
                shell.select_domain("business", navigate_first=False)
            shell.navigate(mid)
        except Exception:
            show_warning(
                self,
                f"打开「{name}」失败。请重启 TOA，或到顶栏「业务」侧栏再点一次。",
            )

    def _on_hide(self) -> None:
        if not self._selected_id:
            return
        try:
            set_plugin_show(self._selected_id, False)
            request_nav_rebuild()
            self.reload()
            show_success(self, "已从侧栏隐藏。")
        except Exception as exc:
            show_error(self, str(exc))

    def _on_remove(self) -> None:
        if not self._selected_id:
            return
        name = self._selected_name or self._selected_id
        if not ask_confirm(
            self,
            f"移除扩展「{name}」？\n\n"
            "将取消侧栏登记、删除扩展文件夹，并清理智能体工作区记录。\n"
            "不会卸载 TOA，也不影响官方功能。",
            title="移除扩展",
        ):
            return
        try:
            uninstall_extension(
                self._selected_id,
                root=self._selected_root or None,
            )
            self.reload()
            show_success(self, f"「{name}」已移除。")
            self._page.report_status(f"已移除扩展「{name}」")
        except Exception as exc:
            show_error(self, f"移除失败：{exc}")

    def _on_folder(self) -> None:
        if self._selected_root:
            open_in_file_manager(self._selected_root)

    def _on_export(self) -> None:
        if not self._selected_root:
            return
        from PySide6.QtWidgets import QFileDialog

        default_name = f"{self._selected_id or 'extension'}.toa-ext.zip"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出扩展包",
            default_name,
            "TOA 扩展包 (*.toa-ext.zip);;Zip (*.zip)",
        )
        if not path:
            return
        try:
            result = export_extension_zip(self._selected_root, path)
            show_success(self, f"已导出：{result.zip_path}")
            self._page.report_status(f"已导出扩展包「{result.plugin_id}」")
        except Exception as exc:
            show_error(self, f"导出失败：{exc}")

    def _on_upload_cloud(self) -> None:
        if not self._selected_root:
            return
        name = self._selected_name or self._selected_id
        if not ask_confirm(
            self,
            f"将「{name}」投稿到运营台社区？\n\n"
            "无偿流通：任意用户可上传；审核通过后其他人可在「插件市场」下载。",
            title="上传社区",
        ):
            return
        try:
            asset = submit_extension_to_cloud(self._selected_root)
            show_success(
                self,
                f"已投稿「{asset.get('name') or name}」"
                f"（状态：{asset.get('review_status') or 'submitted'}）。\n"
                "请等待运营台审核上架。",
            )
            self._page.report_status(f"已上传扩展「{name}」到运营台")
        except Exception as exc:
            show_error(self, f"上传失败：{exc}")

    def _clear_cards(self) -> None:
        """重建网格，避免 GridBox 计数残留。"""
        lay = self._cards_scroll.content_layout
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._cards_grid = GridBox(columns=2, spacing=12)
        lay.addWidget(self._cards_grid)
        lay.addStretch(1)

    def _on_pick_card(self, asset: dict) -> None:
        self._selected_asset_id = int(asset.get("id") or 0)
        self._selected_asset_name = str(
            asset.get("name") or asset.get("plugin_id") or ""
        )
        self._tip.setText(f"社区插件「{self._selected_asset_name}」")

    def _on_community_search(self) -> None:
        q = self._community_q.text().strip()
        try:
            rows = list_public_plugins(q=q)
        except Exception as exc:
            self._community_rows = []
            self._clear_cards()
            self._cards_empty.setVisible(True)
            self._cards_empty.setText(f"社区检索失败：{exc}")
            self._selected_asset_id = 0
            self._tip.setText(f"社区检索失败：{exc}")
            return

        self._community_rows = rows
        self._clear_cards()
        self._selected_asset_id = 0
        self._selected_asset_name = ""

        if not rows:
            self._cards_empty.setVisible(True)
            self._cards_empty.setText(
                "暂无公示插件。在「自定义插件」页上传本机扩展，经运营台审核后出现于此。"
            )
            self._tip.setText("暂无公示插件。")
            return

        self._cards_empty.setVisible(False)
        for row in rows:
            card = _MarketPluginCard(row)
            card.download_clicked.connect(self._on_card_download)
            self._cards_grid.add_widget(card)

        self._tip.setText(f"社区公示 {len(rows)} 个插件（无偿）。点卡片右侧「下载」安装。")

    def _on_card_download(self, asset: dict) -> None:
        self._on_pick_card(asset)
        self._on_community_download(open_after=False, asset=asset)

    def _on_community_download(
        self, open_after: bool = False, asset: dict | None = None
    ) -> None:
        row = asset or {}
        asset_id = int(row.get("id") or self._selected_asset_id or 0)
        title = str(
            row.get("name")
            or self._selected_asset_name
            or row.get("plugin_id")
            or asset_id
        )
        if not asset_id:
            show_warning(self, "请点击卡片上的「下载」")
            return
        try:
            pid, name = download_and_install_plugin(asset_id, show=False)
            self._tabs.setCurrentIndex(0)
            self.reload()
            for local in self._rows:
                if local.get("id") == pid:
                    self._apply_selection(local)
                    break
            if open_after:
                try:
                    mark_development_done(pid)
                    self.reload()
                    for local in self._rows:
                        if local.get("id") == pid:
                            self._apply_selection(local)
                            break
                    self._on_open()
                except Exception as exc:
                    show_warning(
                        self,
                        f"已下载「{name}」，自动打开失败：{exc}\n"
                        "请在「自定义插件」页点「开发完成」后打开。",
                    )
            else:
                show_success(
                    self,
                    f"已下载「{name}」。在「自定义插件」页点「开发完成」后出现在业务侧栏。",
                )
            self._page.report_status(f"已下载社区插件「{title}」")
        except Exception as exc:
            show_error(self, f"下载失败：{exc}")

    def _on_import(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入扩展包",
            "",
            "TOA 扩展包 (*.toa-ext.zip *.zip);;All (*.*)",
        )
        if not path:
            return
        try:
            result = import_extension_zip(path, show=False)
            self.reload()
            for row in self._rows:
                if row.get("id") == result.plugin_id:
                    self._apply_selection(row)
                    break
            show_success(
                self,
                f"已导入「{result.name}」。点「开发完成」后才会出现在业务侧栏。",
            )
            self._page.report_status(f"已导入扩展「{result.name}」")
        except Exception as exc:
            show_error(self, f"导入失败：{exc}")
