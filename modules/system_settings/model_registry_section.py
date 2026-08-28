# -*- coding: utf-8 -*-
"""系统设置 · 模型管理（统一表格）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.base_page import BasePage
from core.user_messages import show_info, show_warning
from services.integrations.config import load_integrations_config, save_integrations_config
from services.integrations.secrets import get_profile_secret, set_profile_secret, set_secret
from services.model_catalog import (
    get_active_profile_id,
    save_user_profile_patch,
    set_active_profile_id,
)
from services.model_registry_view import build_registry_rows
from services.model_ready_registry import ReadyStatus
from widgets import (
    ComboBox,
    DataTable,
    HintLabel,
    LineEdit,
    PasswordLineEdit,
    PrimaryButton,
    SecondaryButton,
)
from widgets.themed_labels import SectionTitle

_COLS = ("名称", "供应商", "类型", "URL", "模型名", "状态", "Key", "默认")


class ModelRegistrySection(QWidget):
    """一张表管理文本/图像等模型 profile。"""

    def __init__(self, parent: BasePage) -> None:
        super().__init__(parent)
        self._page = parent
        self._rows: list[dict] = []
        self._filter_cap: str | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        list_header = QHBoxLayout()
        list_header.setSpacing(8)
        list_header.addWidget(SectionTitle("模型列表"))
        list_header.addStretch(1)
        list_header.addWidget(HintLabel("类型"))
        self._filter_combo = ComboBox()
        self._filter_combo.setMinimumWidth(112)
        self._filter_combo.setMaximumWidth(140)
        self._filter_combo.addItem("全部", "")
        self._filter_combo.addItem("文本", "text_llm")
        self._filter_combo.addItem("图片", "image_gen")
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        list_header.addWidget(self._filter_combo)
        btn_refresh = SecondaryButton("刷新")
        btn_refresh.clicked.connect(lambda: self.refresh(report=True))
        list_header.addWidget(btn_refresh)
        lay.addLayout(list_header)

        self._table = DataTable()
        self._table.set_headers(list(_COLS))
        self._table.setMinimumHeight(280)
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        lay.addWidget(self._table, 1)
        self._table.itemSelectionChanged.connect(self._on_row_selected)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        lay.addWidget(sep)

        detail = QWidget()
        detail.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        detail_lay = QVBoxLayout(detail)
        detail_lay.setContentsMargins(0, 6, 0, 0)
        detail_lay.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(SectionTitle("编辑"))
        self._name_label = HintLabel("—")
        self._name_label.setWordWrap(False)
        self._name_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        head.addWidget(self._name_label, 1)
        btn_save = PrimaryButton("保存")
        btn_save.clicked.connect(self._save_selected)
        head.addWidget(btn_save)
        btn_default = SecondaryButton("设为默认")
        btn_default.clicked.connect(self._set_default)
        head.addWidget(btn_default)
        btn_test = SecondaryButton("测试连通")
        btn_test.clicked.connect(self._test_selected)
        head.addWidget(btn_test)
        btn_clear = SecondaryButton("清除 Key")
        btn_clear.clicked.connect(self._clear_key)
        head.addWidget(btn_clear)
        detail_lay.addLayout(head)

        self._detail_hint = HintLabel("从上方表格选择一行进行编辑。")
        self._detail_hint.setWordWrap(True)
        detail_lay.addWidget(self._detail_hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(3, 2)

        url_lbl = HintLabel("URL")
        url_lbl.setWordWrap(False)
        grid.addWidget(url_lbl, 0, 0)
        self._url = LineEdit()
        self._url.setPlaceholderText("https://api.deepseek.com/v1 或 http://127.0.0.1:11434/v1")
        grid.addWidget(self._url, 0, 1)
        model_lbl = HintLabel("模型名")
        model_lbl.setWordWrap(False)
        grid.addWidget(model_lbl, 0, 2)
        self._model = LineEdit()
        self._model.setPlaceholderText("如 kimi-k2.6、deepseek-chat、dall-e-3")
        grid.addWidget(self._model, 0, 3)

        key_lbl = HintLabel("API Key")
        key_lbl.setWordWrap(False)
        grid.addWidget(key_lbl, 1, 0)
        self._key = PasswordLineEdit()
        self._key.setPlaceholderText("留空保留原 Key；本地 Ollama 通常不需要")
        grid.addWidget(self._key, 1, 1, 1, 3)
        detail_lay.addLayout(grid)
        lay.addWidget(detail, 0)

        self.refresh(report=False)

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

    def refresh(self, *, report: bool = True) -> None:
        self._rows = build_registry_rows(capability_filter=self._filter_cap)
        table_rows: list[tuple[str, ...]] = []
        for row in self._rows:
            url = str(row.get("url") or "—")
            if len(url) > 40:
                url = url[:37] + "…"
            table_rows.append(
                (
                    str(row.get("label") or ""),
                    str(row.get("vendor") or "—"),
                    str(row.get("type") or ""),
                    url,
                    str(row.get("model") or "—"),
                    str(row.get("status") or ""),
                    str(row.get("key") or ""),
                    "★" if row.get("is_default") else "",
                )
            )
        self._table.set_rows(table_rows)
        for r, row_meta in enumerate(self._rows):
            for c in range(self._table.columnCount()):
                item = self._table.item(r, c)
                if item is not None:
                    item.setData(Qt.ItemDataRole.UserRole, row_meta)
        if self._rows:
            self._table.selectRow(0)
        else:
            self._clear_detail()
        if report:
            self._page.report_status(f"模型列表 {len(self._rows)} 条")

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

    def _on_row_selected(self) -> None:
        row = self._selected_row()
        if not row:
            self._clear_detail()
            return
        self._name_label.setText(
            f"{row.get('label')} · {row.get('vendor')} · {row.get('type')}"
        )
        self._url.setText(str(row.get("url") or ""))
        self._model.setText(str(row.get("model") or ""))
        hint = str(row.get("hint") or "").strip()
        status = str(row.get("status") or "")
        if hint:
            self._detail_hint.setText(f"{status} — {hint}")
        else:
            self._detail_hint.setText(status or "—")
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
        self._url.clear()
        self._model.clear()
        self._key.clear()
        self._detail_hint.setText("从上方表格选择一行进行编辑。")

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
        base = self._url.text().strip()
        model = self._model.text().strip()
        if cap == "text_llm" and (not base or not model):
            show_warning(self._page, "文本模型须填写 URL 与模型名。")
            return
        if cap == "image_gen" and not base:
            show_warning(self._page, "图像模型须填写 URL（或本地服务地址）。")
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
        self._page.report_status(f"已设为默认：{row.get('label')}")

    def _test_selected(self) -> None:
        row = self._selected_row()
        if not row or not row.get("catalog"):
            show_warning(self._page, "本机权重文件不支持连通测试。")
            return
        cap = str(row.get("capability") or "")
        pid = str(row.get("profile_id") or "")
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
            show_info(
                self._page,
                "图像模型：请确认本地 WebUI 已启动并开启 API，或在媒体工坊试生成一张图。",
            )
        else:
            show_info(self._page, "该类型暂不支持一键测试。")

    def _clear_key(self) -> None:
        row = self._selected_row()
        if not row or not row.get("catalog"):
            return
        cap = str(row.get("capability") or "")
        pid = str(row.get("profile_id") or "")
        set_profile_secret(cap, pid, "api_key", "")
        if cap == "text_llm" and pid == "moonshot_kimi":
            set_secret("llm", "api_key", "")
        self._key.clear()
        self.refresh(report=False)
        show_info(self._page, "已清除本机 Key。")
