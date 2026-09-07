# -*- coding: utf-8 -*-
"""网页工作台：内嵌浏览器，可配置并切换多个在线文档/网页地址。"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QUrl, Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.base_dialog import BaseDialog
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from core.user_messages import show_warning
from modules.web_workspace.workspace_store import (
    add_site,
    delete_site,
    get_site,
    get_zoom_factor,
    invalidate_cache,
    list_sites,
    load_workspace,
    normalize_url,
    set_last_site,
    set_zoom_factor,
    update_site,
)
from widgets import ComboBox, HintLabel, SecondaryButton
from widgets.list_edit import FormEditDialog, ListPanel, confirm_delete

_ZOOM_STEPS = (0.9, 1.0, 1.1, 1.25, 1.4)


def _webengine_available() -> bool:
    from services.qt_webengine_bootstrap import webengine_import_ok

    return webengine_import_ok()


class _WebWorkspaceF11Filter(QObject):
    """WebEngine 内把 F11 交给壳层沉浸，避免浏览器自吃全屏键。"""

    def __init__(self, page: "WebWorkspacePage") -> None:
        super().__init__(page)
        self._page = page

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() not in (QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride):
            return False
        if event.key() != Qt.Key.Key_F11 or event.modifiers() != Qt.KeyboardModifier.NoModifier:
            return False
        shell = self._page.window()
        if shell is None or not hasattr(shell, "_toggle_fullscreen"):
            return False
        if event.type() == QEvent.Type.ShortcutOverride:
            event.accept()
        else:
            shell._toggle_fullscreen()
        return True


class _SitesManageDialog(BaseDialog):
    dialog_kind = "medium"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("管理站点")
        self._ids: list[str] = []

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(HintLabel("选中站点后点「设为当前」或双击条目；也可在主界面下拉框切换。"))

        self._panel = ListPanel(
            add_label="新增",
            edit_label="编辑",
            delete_label="删除",
            show_refresh=True,
            refresh_label="刷新",
            hint="",
        )
        self._panel.bind_add(self._on_add)
        self._panel.bind_edit(self._on_edit)
        self._panel.bind_delete(self._on_delete)
        self._panel.bind_refresh(self._reload)
        self._panel.list_widget.itemDoubleClicked.connect(lambda _item: self.accept())
        lay.addWidget(self._panel, 1)

        from widgets.dialog_actions import DialogButtonRow

        row = DialogButtonRow()
        row.add_secondary("设为当前", self.accept)
        row.add_primary("完成", self.accept)
        lay.addWidget(row)
        self._reload()

    def selected_site_id(self) -> str:
        row = self._panel.current_row()
        if 0 <= row < len(self._ids):
            return self._ids[row]
        return ""

    def _reload(self) -> None:
        sites = list_sites()
        self._ids = [str(s.get("id") or "") for s in sites]
        labels = [f"{s.get('name') or '未命名'}  ·  {s.get('url')}" for s in sites]
        self._panel.set_items(labels)

    def _on_add(self) -> None:
        dlg = FormEditDialog(
            self,
            title="新增站点",
            fields=[("名称", "name"), ("地址 URL", "url")],
            ok_text="添加",
        )
        dlg.set_values({"name": "", "url": "https://"})
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.values()
        name = str(vals.get("name") or "").strip()
        url = str(vals.get("url") or "").strip()
        if not name:
            show_warning(self, "请填写名称。")
            return
        try:
            add_site(name, url)
        except ValueError as exc:
            show_warning(self, str(exc))
            return
        self._reload()

    def _on_edit(self) -> None:
        row = self._panel.current_row()
        if row < 0 or row >= len(self._ids):
            show_warning(self, "请先选择一条站点。")
            return
        sid = self._ids[row]
        site = get_site(sid)
        if site is None:
            show_warning(self, "站点不存在。")
            self._reload()
            return
        dlg = FormEditDialog(
            self,
            title="编辑站点",
            fields=[("名称", "name"), ("地址 URL", "url")],
        )
        dlg.set_values({"name": site.get("name"), "url": site.get("url")})
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.values()
        name = str(vals.get("name") or "").strip()
        url = str(vals.get("url") or "").strip()
        if not name:
            show_warning(self, "请填写名称。")
            return
        try:
            update_site(sid, name=name, url=url)
        except ValueError as exc:
            show_warning(self, str(exc))
            return
        self._reload()

    def _on_delete(self) -> None:
        row = self._panel.current_row()
        if row < 0 or row >= len(self._ids):
            show_warning(self, "请先选择一条站点。")
            return
        sid = self._ids[row]
        site = get_site(sid) or {}
        if not confirm_delete(self, f"确定删除「{site.get('name') or sid}」？"):
            return
        delete_site(sid)
        self._reload()


class WebWorkspacePage(BasePage):
    page_id = "web_workspace"
    page_title = "网页工作台"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._view = None
        self._profile = None
        self._site_ids: list[str] = []
        self._ready = _webengine_available()

        m = page_content_margins()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*m)
        outer.setSpacing(8)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(HintLabel("站点"))
        self._combo = ComboBox()
        self._combo.setMinimumWidth(220)
        self._combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._combo.currentIndexChanged.connect(self._on_combo_changed)
        self._combo.activated.connect(self._on_combo_changed)
        bar.addWidget(self._combo, 1)

        self._btn_refresh = SecondaryButton("刷新")
        self._btn_refresh.clicked.connect(self._reload_page)
        bar.addWidget(self._btn_refresh)

        bar.addWidget(HintLabel("显示"))
        self._btn_zoom_out = SecondaryButton("−")
        self._btn_zoom_out.setToolTip("缩小（表格字更小）")
        self._btn_zoom_out.setFixedWidth(36)
        self._btn_zoom_out.clicked.connect(lambda: self._nudge_zoom(-1))
        bar.addWidget(self._btn_zoom_out)
        self._btn_zoom_label = SecondaryButton("100%")
        self._btn_zoom_label.setToolTip("点击恢复 100%；表格字发虚时可试 110%/125%")
        self._btn_zoom_label.setMinimumWidth(56)
        self._btn_zoom_label.clicked.connect(lambda: self._apply_zoom(1.0))
        bar.addWidget(self._btn_zoom_label)
        self._btn_zoom_in = SecondaryButton("+")
        self._btn_zoom_in.setToolTip("放大（表格字更清晰好读）")
        self._btn_zoom_in.setFixedWidth(36)
        self._btn_zoom_in.clicked.connect(lambda: self._nudge_zoom(1))
        bar.addWidget(self._btn_zoom_in)

        self._btn_manage = SecondaryButton("管理站点")
        self._btn_manage.clicked.connect(self._manage_sites)
        bar.addWidget(self._btn_manage)

        self._btn_home = SecondaryButton("在浏览器打开")
        self._btn_home.clicked.connect(self._open_external)
        bar.addWidget(self._btn_home)
        outer.addLayout(bar)

        self._host = QWidget()
        self._host.setObjectName("WebWorkspaceHost")
        self._host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        host_lay = QVBoxLayout(self._host)
        host_lay.setContentsMargins(0, 0, 0, 0)
        self._placeholder = QLabel(
            "正在加载浏览器组件…"
            if self._ready
            else "当前安装包未包含内嵌浏览器组件，请点右上角「在浏览器打开」。"
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        host_lay.addWidget(self._placeholder, 1)
        outer.addWidget(self._host, 1)

        self._reload_combo()

    def primary_focus_widget(self):
        return self._combo

    def on_enter(self) -> None:
        invalidate_cache()
        self._reload_combo(select_last=True)
        if self._ready:
            self._ensure_view()
            self._load_current_site()

    def soft_leave(self) -> None:
        """壳层切走：停加载；View 由壳层延迟 purge。"""
        view = self._view
        if view is None:
            return
        try:
            from PySide6.QtWebEngineCore import QWebEnginePage

            page = view.page()
            if page is not None:
                page.triggerAction(QWebEnginePage.WebAction.Stop)
        except Exception:
            pass

    def on_leave(self) -> None:
        self.soft_leave()

    def uses_webengine_embed(self) -> bool:
        return self._view is not None

    def keep_web_embed_on_leave(self) -> bool:
        return False

    def _destroy_web_embed(self) -> None:
        """壳层延迟调用：拆内嵌 WebEngine，避免与其它引擎页并存闪退。"""
        from PySide6.QtCore import QTimer

        view = self._view
        self._view = None
        if view is None:
            return
        try:
            from PySide6.QtWidgets import QApplication

            fw = QApplication.focusWidget()
            if fw is not None and (fw is view or view.isAncestorOf(fw)):
                fw.clearFocus()
        except Exception:
            pass
        try:
            view.hide()
        except Exception:
            pass
        try:
            view.loadStarted.disconnect()
        except Exception:
            pass
        try:
            view.loadFinished.disconnect()
        except Exception:
            pass
        try:
            from PySide6.QtWebEngineCore import QWebEnginePage

            page = view.page()
            if page is not None:
                page.triggerAction(QWebEnginePage.WebAction.Stop)
            view.setPage(None)
        except Exception:
            pass
        try:
            view.setParent(None)
        except Exception:
            pass
        try:
            self._placeholder.show()
        except Exception:
            pass
        QTimer.singleShot(400, lambda v=view: self._delete_view_later(v))

    @staticmethod
    def _delete_view_later(view) -> None:
        try:
            from shiboken6 import isValid

            if view is None or not isValid(view):
                return
        except Exception:
            pass
        try:
            view.deleteLater()
        except RuntimeError:
            pass
        except Exception:
            pass

    def _ensure_view(self) -> None:
        if self._view is not None:
            return
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
        from PySide6.QtWebEngineWidgets import QWebEngineView

        from services.storage_paths import module_data_dir

        profile_dir = module_data_dir("web_workspace", create=True) / "browser_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._profile = QWebEngineProfile("toa3_web_workspace", self)
        self._profile.setPersistentStoragePath(str(profile_dir))
        self._profile.setCachePath(str(profile_dir / "cache"))

        self._view = QWebEngineView(self._host)
        page = QWebEnginePage(self._profile, self._view)
        self._view.setPage(page)
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._view.loadStarted.connect(lambda: self.report_status("正在加载…", level=StatusLevel.INFO))
        self._view.loadFinished.connect(self._on_load_finished)

        settings = self._view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        # 略提高默认字号下限，减轻文档里 9pt 发虚观感（不改页面布局字号策略）
        settings.setFontFamily(QWebEngineSettings.FontFamily.StandardFont, "Microsoft YaHei UI")
        settings.setFontFamily(QWebEngineSettings.FontFamily.SansSerifFont, "Microsoft YaHei UI")
        settings.setFontSize(QWebEngineSettings.FontSize.DefaultFontSize, 14)
        settings.setFontSize(QWebEngineSettings.FontSize.MinimumFontSize, 10)

        lay = self._host.layout()
        if lay is not None:
            self._placeholder.hide()
            lay.addWidget(self._view, 1)
        self._f11_filter = _WebWorkspaceF11Filter(self)
        self._view.installEventFilter(self._f11_filter)
        self._apply_zoom(get_zoom_factor())

    def _apply_zoom(self, zoom: float) -> None:
        z = set_zoom_factor(zoom)
        if self._view is not None:
            self._view.setZoomFactor(z)
        self._btn_zoom_label.setText(f"{int(round(z * 100))}%")
        self.report_status(f"网页缩放 {int(round(z * 100))}%", level=StatusLevel.INFO)

    def _nudge_zoom(self, direction: int) -> None:
        cur = get_zoom_factor()
        # 找最近档位再步进
        nearest = min(_ZOOM_STEPS, key=lambda x: abs(x - cur))
        idx = _ZOOM_STEPS.index(nearest)
        idx = max(0, min(len(_ZOOM_STEPS) - 1, idx + int(direction)))
        self._apply_zoom(_ZOOM_STEPS[idx])

    def _on_load_finished(self, ok: bool) -> None:
        if self._view is not None:
            self._view.setZoomFactor(get_zoom_factor())
            # 阻止页面把 F11 当成浏览器全屏
            self._view.page().runJavaScript(
                "document.addEventListener('keydown',function(e){"
                "if(e.key==='F11'){e.preventDefault();e.stopImmediatePropagation();}},true);"
            )
        if ok:
            self.report_status("页面就绪", level=StatusLevel.SUCCESS)
        else:
            self.report_status("页面加载失败，可点刷新重试", level=StatusLevel.WARNING)

    def _reload_combo(self, *, select_last: bool = False) -> None:
        sites = list_sites()
        self._site_ids = [str(s.get("id") or "") for s in sites]
        self._combo.blockSignals(True)
        self._combo.clear()
        for s in sites:
            self._combo.addItem(str(s.get("name") or s.get("url") or "未命名"), str(s.get("id")))
        self._combo.blockSignals(False)

        if not sites:
            self._combo.addItem("（请添加站点）", "")
            self._btn_refresh.setEnabled(False)
            return
        self._btn_refresh.setEnabled(True)
        last = str(load_workspace().get("last_id") or "")
        idx = self._site_ids.index(last) if last in self._site_ids else 0
        if select_last and idx >= 0:
            self._combo.setCurrentIndex(idx)

    def _current_site_id(self) -> str:
        idx = self._combo.currentIndex()
        if idx < 0 or idx >= len(self._site_ids):
            return ""
        return self._site_ids[idx]

    def _on_combo_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._site_ids):
            return
        sid = self._site_ids[index]
        if not sid:
            return
        set_last_site(sid)
        if self._ready:
            self._ensure_view()
        self._load_current_site()

    def _load_current_site(self) -> None:
        if self._ready:
            self._ensure_view()
        if self._view is None:
            return
        sid = self._current_site_id()
        site = get_site(sid)
        if site is None:
            return
        url = str(site.get("url") or "").strip()
        if not url:
            return
        try:
            normalize_url(url)
        except ValueError as exc:
            show_warning(self, str(exc))
            return
        qurl = QUrl(url)
        if self._placeholder is not None:
            self._placeholder.hide()
        if self._view.url().toString() != qurl.toString():
            self._view.setUrl(qurl)
        else:
            self._view.reload()
        self.report_status(f"正在打开：{site.get('name') or url}", level=StatusLevel.INFO)

    def _reload_page(self) -> None:
        if self._view is None:
            self._load_current_site()
            return
        self._view.reload()

    def _manage_sites(self) -> None:
        dlg = _SitesManageDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        invalidate_cache()
        pick = dlg.selected_site_id() or self._current_site_id()
        self._reload_combo(select_last=False)
        if pick and pick in self._site_ids:
            idx = self._site_ids.index(pick)
            self._combo.blockSignals(True)
            self._combo.setCurrentIndex(idx)
            self._combo.blockSignals(False)
            set_last_site(pick)
        elif self._site_ids:
            self._combo.setCurrentIndex(0)
            set_last_site(self._site_ids[0])
        if self._ready:
            self._ensure_view()
        self._load_current_site()

    def _open_external(self) -> None:
        sid = self._current_site_id()
        site = get_site(sid)
        if site is None:
            show_warning(self, "请先配置并选择一个站点。")
            return
        url = str(site.get("url") or "").strip()
        if not url:
            return
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(url))
