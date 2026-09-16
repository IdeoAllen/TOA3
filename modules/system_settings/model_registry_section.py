# -*- coding: utf-8 -*-
"""系统设置 · 算力来源（模型 profile 统一表格）。"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.base_page import BasePage
from core.user_messages import ask_confirm, show_info, show_warning
from services.integrations.config import load_integrations_config, save_integrations_config
from services.integrations.secrets import get_profile_secret, set_profile_secret, set_secret
from services.model_catalog import (
    get_active_profile_id,
    save_user_profile_patch,
    set_active_profile_id,
)
from services.compute_source import unbind_profile
from services.model_presentation import is_evolink_image_profile, registry_summary
from services.model_registry_view import build_registry_rows
from services.model_ready_registry import ReadyStatus, refresh_local_endpoint_probes
from widgets import (
    ComboBox,
    DataTable,
    FormRow,
    FormSection,
    HintLabel,
    LineEdit,
    PasswordLineEdit,
    PrimaryButton,
    SecondaryButton,
    SectionTitle,
    SplitPane,
    TabWidget,
)

_COLS = ("名称", "区域", "类型", "状态", "Key", "默认")


class _EndpointProbeWorker(QObject):
    finished = Signal()

    def __init__(self, *, deep: bool, force: bool) -> None:
        super().__init__()
        self._deep = deep
        self._force = force

    def run(self) -> None:
        try:
            refresh_local_endpoint_probes(deep=self._deep, force=self._force)
        except Exception:
            pass
        self.finished.emit()


class _ImageConnectWorker(QObject):
    finished = Signal(object)

    def __init__(self, profile_id: str, *, evolink: bool) -> None:
        super().__init__()
        self._profile_id = profile_id
        self._evolink = evolink

    def run(self) -> None:
        try:
            from services.integrations import get_client
            from services.model_catalog import save_user_profile_patch

            pid = self._profile_id
            if self._evolink:
                save_user_profile_patch(
                    "image_gen",
                    pid,
                    {"resolution": "1K", "quality": "low", "n": 1},
                )
            client = get_client("image_gen")
            path = client.generate(
                "连通测试：小蓝色方块，无文字",
                width=512,
                height=512,
                profile_id=pid,
            )
            self.finished.emit(str(path))
        except Exception as exc:
            self.finished.emit(exc)


class ModelRegistrySection(QWidget):
    """一张表管理文本/图像等模型 profile。"""

    def __init__(self, parent: BasePage) -> None:
        super().__init__(parent)
        self._page = parent
        self._rows: list[dict] = []
        self._filter_cap: str | None = None
        self._filter_origin: str | None = None
        self._filter_region: str | None = None
        self._test_thread: QThread | None = None
        self._test_worker: _ImageConnectWorker | None = None
        self._probe_thread: QThread | None = None
        self._probe_worker: _EndpointProbeWorker | None = None
        self._probe_pending_report = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        list_box = FormSection("算力来源")
        list_box.add_widget(
            HintLabel(
                "左侧选模型，右侧填 URL / Token；URL 与模型名在详情区完整展示，表格只保留概览。"
            )
        )

        self._origin_tabs = TabWidget()
        self._origin_tabs.addTab(QWidget(), "全部")
        self._origin_tabs.addTab(QWidget(), "云端 API")
        self._origin_tabs.addTab(QWidget(), "本机平台")
        self._origin_tabs.currentChanged.connect(self._on_origin_tab)
        list_box.add_widget(self._origin_tabs)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        toolbar.addWidget(HintLabel("能力"))
        self._filter_combo = ComboBox()
        self._filter_combo.setMinimumWidth(112)
        self._filter_combo.addItem("全部", "")
        self._filter_combo.addItem("文本", "text_llm")
        self._filter_combo.addItem("图片", "image_gen")
        self._filter_combo.addItem("视频", "video_gen")
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self._filter_combo)
        toolbar.addWidget(HintLabel("区域"))
        self._region_combo = ComboBox()
        self._region_combo.setMinimumWidth(112)
        self._region_combo.addItem("全部", "")
        self._region_combo.addItem("国内", "cn")
        self._region_combo.addItem("国外", "intl")
        self._region_combo.addItem("本机", "local")
        self._region_combo.currentIndexChanged.connect(self._on_region_changed)
        toolbar.addWidget(self._region_combo)
        toolbar.addStretch(1)
        self._btn_refresh = SecondaryButton("刷新")
        self._btn_refresh.clicked.connect(lambda: self.refresh(report=True, probe="deep"))
        toolbar.addWidget(self._btn_refresh)
        list_box.add_layout(toolbar)

        self._summary_label = HintLabel("")
        self._summary_label.setWordWrap(True)
        list_box.add_widget(self._summary_label)

        body_split = SplitPane()
        body_split.setChildrenCollapsible(False)

        list_panel = QWidget()
        list_panel.setMinimumWidth(280)
        list_lay = QVBoxLayout(list_panel)
        list_lay.setContentsMargins(0, 0, 0, 0)
        list_lay.setSpacing(0)
        self._table = DataTable()
        self._table.set_headers(list(_COLS))
        self._table.setMinimumHeight(220)
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        list_lay.addWidget(self._table, 1)
        body_split.addWidget(list_panel)

        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        detail_host = QWidget()
        detail_host.setMinimumWidth(300)
        detail_lay = QVBoxLayout(detail_host)
        detail_lay.setContentsMargins(0, 0, 0, 0)
        detail_lay.setSpacing(8)

        edit_box = FormSection("详情 · 绑定")
        self._name_label = SectionTitle("—")
        edit_box.add_widget(self._name_label)

        self._detail_hint = HintLabel("从左侧表格选择一行。")
        self._detail_hint.setWordWrap(True)
        edit_box.add_widget(self._detail_hint)

        self._meta_row = HintLabel("")
        self._meta_row.setWordWrap(True)
        edit_box.add_widget(self._meta_row)

        self._cloud_form = QWidget()
        form = QFormLayout(self._cloud_form)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._vendor = LineEdit()
        self._vendor.setReadOnly(True)
        self._vendor_label = HintLabel("供应商")
        form.addRow(self._vendor_label, self._vendor)
        self._url = LineEdit()
        self._url.setPlaceholderText("https://api.evolink.ai/v1 或火山方舟 / Moonshot 地址")
        self._url_label = HintLabel("API URL")
        form.addRow(self._url_label, self._url)
        self._model = LineEdit()
        self._model.setPlaceholderText("如 grok-imagine-image-2.0、doubao-seedream-5-0-pro-260628")
        self._model_label = HintLabel("模型名称")
        form.addRow(self._model_label, self._model)
        self._key = PasswordLineEdit()
        self._key.setPlaceholderText("Token / API Key；留空保留原 Key")
        self._key_label = HintLabel("Token / API Key")
        form.addRow(self._key_label, self._key)
        edit_box.add_widget(self._cloud_form)

        self._local_simple_panel = QWidget()
        simple_lay = QHBoxLayout(self._local_simple_panel)
        simple_lay.setContentsMargins(0, 0, 0, 0)
        simple_lay.setSpacing(8)
        btn_setup = PrimaryButton("安装本机模型…")
        btn_setup.clicked.connect(self._open_local_setup)
        simple_lay.addWidget(btn_setup)
        simple_lay.addStretch(1)
        self._local_simple_panel.setVisible(False)
        edit_box.add_widget(self._local_simple_panel)

        actions_top = QHBoxLayout()
        actions_top.setSpacing(8)
        self._btn_save = PrimaryButton("保存")
        self._btn_save.clicked.connect(self._save_selected)
        actions_top.addWidget(self._btn_save)
        self._btn_default = SecondaryButton("设为默认")
        self._btn_default.clicked.connect(self._set_default)
        actions_top.addWidget(self._btn_default)
        actions_top.addStretch(1)
        edit_box.add_layout(actions_top)

        actions_bottom = QHBoxLayout()
        actions_bottom.setSpacing(8)
        self._btn_test = SecondaryButton("测试连通")
        self._btn_test.clicked.connect(self._test_selected)
        actions_bottom.addWidget(self._btn_test)
        self._btn_unbind = SecondaryButton("解绑")
        self._btn_unbind.clicked.connect(self._unbind)
        actions_bottom.addWidget(self._btn_unbind)
        actions_bottom.addStretch(1)
        edit_box.add_layout(actions_bottom)
        detail_lay.addWidget(edit_box)
        detail_lay.addStretch(1)
        detail_scroll.setWidget(detail_host)
        body_split.addWidget(detail_scroll)
        body_split.setStretchFactor(0, 3)
        body_split.setStretchFactor(1, 2)
        body_split.setSizes([480, 360])

        list_box.add_widget(body_split, 1)
        lay.addWidget(list_box, 1)
        self._table.itemSelectionChanged.connect(self._on_row_selected)

        self.refresh(report=False, probe="none")
        QTimer.singleShot(80, lambda: self.refresh(report=False, probe="light"))

    def set_capability_filter(self, capability: str | None) -> None:
        cap = (capability or "").strip() or None
        self._filter_cap = cap
        idx = self._filter_combo.findData(cap or "")
        if idx >= 0:
            self._filter_combo.setCurrentIndex(idx)
        self.refresh(report=False)

    def _on_filter_changed(self, _index: int) -> None:
        data = self._filter_combo.currentData()
        self._filter_cap = str(data or "").strip() or None
        self.refresh(report=False)

    def _on_origin_tab(self, index: int) -> None:
        self._filter_origin = (None, "cloud", "local")[index] if 0 <= index <= 2 else None
        self.refresh(report=False)

    def _on_region_changed(self, _index: int) -> None:
        data = self._region_combo.currentData()
        self._filter_region = str(data or "").strip() or None
        self.refresh(report=False)

    def _cleanup_probe_worker(self) -> None:
        if self._probe_worker is not None:
            self._probe_worker.deleteLater()
            self._probe_worker = None
        if self._probe_thread is not None:
            self._probe_thread.deleteLater()
            self._probe_thread = None

    def _set_probe_busy(self, busy: bool) -> None:
        self._btn_refresh.setEnabled(not busy)

    def _schedule_probe_refresh(self, *, deep: bool, force: bool, report: bool) -> None:
        if self._probe_thread is not None and self._probe_thread.isRunning():
            self._probe_pending_report = self._probe_pending_report or report
            return
        self._probe_pending_report = report
        self._set_probe_busy(True)
        self._probe_thread = QThread(self)
        self._probe_worker = _EndpointProbeWorker(deep=deep, force=force)
        self._probe_worker.moveToThread(self._probe_thread)
        self._probe_thread.started.connect(self._probe_worker.run)

        def _done() -> None:
            pending = self._probe_pending_report
            self._probe_pending_report = False
            self.refresh(report=pending, probe="none")
            if self._probe_thread is not None:
                self._probe_thread.quit()

        self._probe_worker.finished.connect(_done, Qt.ConnectionType.QueuedConnection)
        self._probe_thread.finished.connect(self._cleanup_probe_worker)
        self._probe_thread.finished.connect(lambda: self._set_probe_busy(False))
        self._probe_thread.start()

    def _apply_table(self, *, report: bool) -> None:
        self._rows = build_registry_rows(
            capability_filter=self._filter_cap,
            origin_filter=self._filter_origin,
            region_filter=self._filter_region,
        )
        table_rows: list[tuple[str, ...]] = []
        for row in self._rows:
            table_rows.append(
                (
                    str(row.get("label") or ""),
                    str(row.get("region") or "—"),
                    str(row.get("type") or ""),
                    str(row.get("status") or ""),
                    str(row.get("key") or ""),
                    "★" if row.get("is_default") else "",
                )
            )
        self._table.set_rows(table_rows)
        self._summary_label.setText(registry_summary(self._rows))
        for r, row_meta in enumerate(self._rows):
            tip_parts = [
                str(row_meta.get("label") or ""),
                f"供应商：{row_meta.get('vendor') or '—'}",
                f"URL：{row_meta.get('url') or '—'}",
                f"模型：{row_meta.get('model') or '—'}",
            ]
            tip = "\n".join(tip_parts)
            for c in range(self._table.columnCount()):
                item = self._table.item(r, c)
                if item is not None:
                    item.setData(Qt.ItemDataRole.UserRole, row_meta)
                    if c == 0:
                        item.setToolTip(tip)
        if self._rows:
            self._table.selectRow(0)
        else:
            self._clear_detail()
        if report:
            self._page.report_status(f"模型列表 {len(self._rows)} 条")

    def refresh(self, *, report: bool = True, probe: str = "none") -> None:
        if probe == "deep":
            self._apply_table(report=False)
            self._schedule_probe_refresh(deep=True, force=True, report=report)
            return
        if probe == "light":
            self._apply_table(report=report)
            self._schedule_probe_refresh(deep=False, force=False, report=False)
            return
        self._apply_table(report=report)

    def _selected_row(self) -> dict | None:
        r = self._table.currentRow()
        if 0 <= r < len(self._rows):
            return self._rows[r]
        item = self._table.item(r, 0) if r >= 0 else None
        if item is not None:
            meta = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(meta, dict):
                return meta
        return None

    def _bind_mode(self, row: dict) -> str:
        if not row.get("catalog"):
            return "local_files"
        provider = str(row.get("provider") or "").lower()
        tier = str(row.get("tier") or "").lower()
        if provider == "sdcpp" or tier == "simple":
            return "local_simple"
        if provider in ("comfyui", "sd_webui"):
            return "local_service"
        pid = str(row.get("profile_id") or "").lower()
        url = str(row.get("url") or "").lower()
        if "ollama" in pid or url.startswith("http://127.0.0.1:11434"):
            return "local_ollama"
        return "cloud"

    def _set_form_field_visible(
        self, label: QWidget, field: QWidget, visible: bool
    ) -> None:
        label.setVisible(visible)
        field.setVisible(visible)

    def _apply_edit_mode(self, row: dict) -> None:
        mode = self._bind_mode(row)
        hint = str(row.get("hint") or "").strip()
        code = row.get("status_code")

        if mode == "local_simple":
            self._cloud_form.setVisible(False)
            self._local_simple_panel.setVisible(True)
            self._btn_save.setVisible(False)
            self._btn_test.setVisible(False)
            if code == ReadyStatus.READY:
                self._detail_hint.setText(
                    "已装好，可直接设为默认，去媒体工坊写一句话出图。"
                )
            else:
                extra = f" {hint}" if hint else ""
                self._detail_hint.setText(
                    "不用填 URL 或 Key。点「安装本机生图」一键下载，或自动从 ComfyUI 目录找已有文件。"
                    + extra
                )
            return

        self._local_simple_panel.setVisible(False)
        self._cloud_form.setVisible(True)
        self._btn_save.setVisible(True)
        self._btn_test.setVisible(True)

        if mode == "local_files":
            self._cloud_form.setVisible(False)
            self._btn_save.setVisible(False)
            self._btn_test.setVisible(False)
            self._detail_hint.setText(self._format_detail_hint(row))
            return

        if mode == "local_service":
            self._url.setReadOnly(True)
            self._set_form_field_visible(self._vendor_label, self._vendor, True)
            self._vendor.setText(str(row.get("vendor") or "本机平台"))
            self._url_label.setText("服务地址")
            self._set_form_field_visible(self._url_label, self._url, True)
            self._model_label.setText("模型 / 工作流")
            self._set_form_field_visible(self._model_label, self._model, True)
            self._model.setReadOnly(True)
            self._set_form_field_visible(self._key_label, self._key, False)
            self._btn_save.setVisible(False)
            self._detail_hint.setText(
                hint
                or "地址已内置。请在本机启动服务，再点上方「刷新」检测是否可用。"
            )
            return

        if mode == "local_ollama":
            self._url.setReadOnly(False)
            self._set_form_field_visible(self._vendor_label, self._vendor, True)
            self._vendor.setText(str(row.get("vendor") or "Ollama"))
            self._url_label.setText("服务地址")
            self._set_form_field_visible(self._url_label, self._url, True)
            self._model_label.setText("模型名称")
            self._set_form_field_visible(self._model_label, self._model, True)
            self._model.setReadOnly(False)
            self._set_form_field_visible(self._key_label, self._key, False)
            self._detail_hint.setText(
                hint or "本机 Ollama 跑起来即可，通常不用 Key。模型名需与 ollama pull 的一致。"
            )
            return

        self._url.setReadOnly(False)
        self._model.setReadOnly(False)
        self._set_form_field_visible(self._vendor_label, self._vendor, True)
        self._vendor.setText(str(row.get("vendor") or "—"))
        self._url_label.setText("API URL")
        self._set_form_field_visible(self._url_label, self._url, True)
        self._model_label.setText("模型名称")
        self._set_form_field_visible(self._model_label, self._model, True)
        self._set_form_field_visible(self._key_label, self._key, True)
        self._key_label.setText("Token / API Key")
        self._detail_hint.setText(self._format_detail_hint(row))

    def _format_detail_hint(self, row: dict) -> str:
        status = str(row.get("status") or "").strip()
        code = row.get("status_code")
        if code == ReadyStatus.READY:
            return "已绑定且可用，可设为默认或测试连通。"
        if code == ReadyStatus.NEEDS_KEY:
            return "请填写 API Key 后点保存以完成绑定。"
        if code == ReadyStatus.NEEDS_ENDPOINT:
            return "请填写 API 地址后点保存。"
        if not row.get("catalog"):
            return "本机权重只读，请在 data/models 管理文件。"
        return status or "选中上方一行后可编辑。"

    def _on_row_selected(self) -> None:
        row = self._selected_row()
        if not row:
            self._clear_detail()
            return
        self._name_label.setText(
            f"{row.get('label')} · {row.get('origin')} · {row.get('type')}"
        )
        self._vendor.setText(str(row.get("vendor") or "—"))
        self._url.setText(str(row.get("url") or ""))
        self._model.setText(str(row.get("model") or ""))
        meta = f"区域：{row.get('region')} · 供应商：{row.get('vendor')}"
        hint_text = str(row.get("hint") or "").strip()
        if hint_text:
            meta = f"{meta} · {hint_text}"
        self._meta_row.setText(meta)
        self._apply_edit_mode(row)
        cap = str(row.get("capability") or "")
        pid = str(row.get("profile_id") or "")
        if row.get("catalog") and cap and pid:
            if get_profile_secret(cap, pid):
                self._key.setPlaceholderText("已保存（留空保留原 Key）")
            else:
                self._key.setPlaceholderText("云端供应商通常需要 Key")
        else:
            self._key.setPlaceholderText("本机权重文件，无需 Key")
        self._key.clear()

    def _clear_detail(self) -> None:
        self._name_label.setText("—")
        self._vendor.clear()
        self._url.clear()
        self._model.clear()
        self._key.clear()
        self._meta_row.clear()
        self._cloud_form.setVisible(True)
        self._local_simple_panel.setVisible(False)
        self._btn_save.setVisible(True)
        self._btn_test.setVisible(True)
        self._detail_hint.setText("从左侧表格选择一行。")

    def _open_local_setup(self) -> None:
        from modules.system_settings.local_image_setup_dialog import LocalImageSetupDialog

        dlg = LocalImageSetupDialog(self._page)
        dlg.exec()
        self.refresh(report=False)
        if dlg.ready:
            self._page.report_status("本机生图已就绪")

    def _save_selected(self) -> None:
        row = self._selected_row()
        if not row:
            show_warning(self._page, "请先选择一行。")
            return
        if not row.get("catalog"):
            show_warning(self._page, "本机权重文件只读，请在 data/models 管理文件。")
            return
        cap = str(row.get("capability") or "")
        pid = str(row.get("profile_id") or "")
        mode = self._bind_mode(row)
        if mode in ("local_simple", "local_files", "local_service"):
            show_warning(self._page, "此项不用保存表单。本机生图请导入离线包；Comfy 请先启动服务再刷新。")
            return
        base = self._url.text().strip()
        model = self._model.text().strip()
        if cap == "text_llm" and (not base or not model):
            show_warning(self._page, "文本模型须填写 URL 与模型名。")
            return
        if cap == "image_gen" and mode == "cloud" and not base:
            show_warning(self._page, "云端生图须填写 API 地址。")
            return

        def _do() -> None:
            patch: dict = {"api_base": base, "model": model}
            if cap == "text_llm":
                patch["provider"] = "openai_compatible"
            save_user_profile_patch(cap, pid, patch)
            set_active_profile_id(cap, pid)
            key = self._key.text().strip()
            if key:
                set_profile_secret(cap, pid, "api_key", key)
                if pid == "evolink_grok_imagine":
                    set_profile_secret("video_gen", "evolink_seedance_2", "api_key", key)
                elif pid == "evolink_seedance_2":
                    set_profile_secret("image_gen", "evolink_grok_imagine", "api_key", key)
                elif str(pid).startswith("mxapi_"):
                    for shared in (
                        "mxapi_nano_banana_2",
                        "mxapi_gpt_image_2",
                        "mxapi_nano_banana_pro",
                    ):
                        if shared != pid:
                            set_profile_secret("image_gen", shared, "api_key", key)
                if cap == "text_llm" and pid == "moonshot_kimi":
                    set_secret("llm", "api_key", key)
                self._key.clear()
            if cap == "text_llm":
                save_integrations_config(
                    {
                        "llm": {
                            "enabled": True,
                            "provider": "openai_compatible",
                            "api_base": base,
                            "model": model,
                            "note": "摘要、改写；多配置见 model_catalog",
                        }
                    }
                )
            elif cap == "image_gen":
                save_integrations_config(
                    {
                        "image_gen": {
                            "enabled": True,
                            "provider": "catalog",
                            "note": "文生图；profile 见 model_catalog",
                        }
                    }
                )
            load_integrations_config(force=True)
            self.refresh(report=False)
            integrations = getattr(self._page, "_integrations", None)
            if integrations is not None and hasattr(integrations, "refresh_status"):
                integrations.refresh_status(report=False, probe=False)

        self._page.run_safe(_do, success_status="模型配置已保存")

    def _set_default(self) -> None:
        row = self._selected_row()
        if not row or not row.get("catalog"):
            show_warning(self._page, "请选择 catalog 中的模型配置。")
            return
        cap = str(row.get("capability") or "")
        pid = str(row.get("profile_id") or "")
        if row.get("status_code") != ReadyStatus.READY:
            show_warning(
                self._page,
                f"当前状态：{row.get('status')}。建议先补齐 Key 或端点后再设为默认。",
            )
        set_active_profile_id(cap, pid)
        self.refresh(report=False)
        self._page.report_status(f"已设为默认卡：{row.get('label')}")

    def _cleanup_test_worker(self) -> None:
        if self._test_worker is not None:
            self._test_worker.deleteLater()
            self._test_worker = None
        if self._test_thread is not None:
            self._test_thread.deleteLater()
            self._test_thread = None

    def _set_test_busy(self, busy: bool) -> None:
        self._btn_test.setEnabled(not busy)

    def _start_image_connect_test(self, pid: str, *, evolink: bool, label: str) -> None:
        if self._test_thread is not None and self._test_thread.isRunning():
            show_warning(self._page, "连通测试进行中，请稍候。")
            return
        self._set_test_busy(True)
        self._page.report_status(f"正在测试 {label}…")
        self._test_thread = QThread(self)
        self._test_worker = _ImageConnectWorker(pid, evolink=evolink)
        self._test_worker.moveToThread(self._test_thread)
        self._test_thread.started.connect(self._test_worker.run)

        def _done(result) -> None:
            if isinstance(result, Exception):
                msg = str(getattr(result, "user_message", None) or result)
                show_warning(self._page, f"连通失败：{msg}")
                self._page.report_status("连通测试失败")
            else:
                show_info(
                    self._page,
                    f"{label} 连通正常。\n测试图已保存：\n{result}",
                )
                self._page.report_status(f"{label} 连通正常")
            if self._test_thread is not None:
                self._test_thread.quit()

        self._test_worker.finished.connect(_done, Qt.ConnectionType.QueuedConnection)
        self._test_thread.finished.connect(self._cleanup_test_worker)
        self._test_thread.finished.connect(lambda: self._set_test_busy(False))
        self._test_thread.start()

    def _test_selected(self) -> None:
        row = self._selected_row()
        if not row or not row.get("catalog"):
            show_warning(self._page, "本机权重文件不支持连通测试。")
            return
        cap = str(row.get("capability") or "")
        pid = str(row.get("profile_id") or "")
        mode = self._bind_mode(row)
        if cap == "text_llm":
            from services.integrations import get_client

            client = get_client("llm")
            try:
                text = client.complete(
                    "只用两个字回复：成功",
                    system="你是连通测试助手。",
                    profile_id=pid,
                )
                show_info(self._page, f"文本模型连通正常。\n回复：{text[:80]}")
            except Exception as exc:
                show_warning(self._page, f"连通失败：{exc}")
        elif cap == "image_gen":
            if mode == "local_service":
                refresh_local_endpoint_probes(deep=True, force=True)
                self.refresh(report=False)
                row = self._selected_row() or row
                if row.get("status_code") == ReadyStatus.READY:
                    show_info(self._page, "本机生图服务已检测到在线，可在媒体工坊试跑。")
                else:
                    show_warning(
                        self._page,
                        str(row.get("status") or "未检测到本机服务，请先启动 ComfyUI / WebUI。"),
                    )
                return
            if mode != "cloud":
                show_info(
                    self._page,
                    "本机权重无需连通测试；装好后在媒体工坊直接试生成即可。",
                )
                return
            if row.get("status_code") == ReadyStatus.NEEDS_KEY:
                show_warning(self._page, "请先保存 API Key 后再测试。")
                return
            label = str(row.get("label") or pid)
            evolink = is_evolink_image_profile(row, pid)
            cost_hint = (
                "将发起一次低成本测试（1K · 低画质 · 约 $0.03）。"
                if evolink
                else "将发起一次小图连通测试（可能产生少量 API 费用）。"
            )
            if not ask_confirm(
                self._page,
                f"{cost_hint}\n确认测试「{label}」？",
                title="图像连通测试",
            ):
                return
            self._start_image_connect_test(pid, evolink=evolink, label=label)
        elif cap == "video_gen":
            if mode == "cloud" and row.get("status_code") == ReadyStatus.NEEDS_KEY:
                show_warning(self._page, "请先保存 API Key 后再测试。")
                return
            show_info(
                self._page,
                "视频模型：请在媒体工坊提交一条短视频任务验证；"
                "完整连通测试会产生较高费用，暂不提供一键跑通。",
            )
        else:
            show_info(self._page, "该类型暂不支持一键测试。")

    def _unbind(self) -> None:
        row = self._selected_row()
        if not row or not row.get("catalog"):
            show_warning(self._page, "请选择可解绑的算力来源。")
            return
        cap = str(row.get("capability") or "")
        pid = str(row.get("profile_id") or "")
        label = str(row.get("label") or pid)
        if not ask_confirm(
            self._page,
            f"解绑「{label}」？\n云端将清除本机 Key；本机来源仅取消默认，不删模型文件。",
            title="解绑算力来源",
        ):
            return
        ok, msg = unbind_profile(cap, pid)
        self._key.clear()
        self.refresh(report=False)
        if ok:
            show_info(self._page, msg)
            self._page.report_status(f"已解绑：{label}")
        else:
            show_warning(self._page, msg)
