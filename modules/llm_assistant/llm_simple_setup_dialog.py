# -*- coding: utf-8 -*-
"""大模型助手 · 简单配置（≤2 步 · 持久化）。"""
from __future__ import annotations

from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QVBoxLayout, QWidget

from core.base_dialog import BaseDialog
from core.user_messages import show_success, show_warning
from services.model_catalog import list_profiles, resolve_profile
from widgets import (
    DialogButtonRow,
    HintLabel,
    LineEdit,
    PasswordLineEdit,
    PrimaryButton,
    RadioButton,
)


# 范式预设：三选一，覆盖 catalog 主流写字来源
_SIMPLE_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("moonshot_kimi", "Moonshot · Kimi", "cloud"),
    ("deepseek", "DeepSeek · Chat", "cloud"),
    ("ollama_local", "本机 Ollama", "local_ollama"),
)


def bind_text_llm_simple(
    profile_id: str,
    *,
    api_key: str = "",
    model: str = "",
    api_base: str = "",
) -> tuple[bool, str]:
    """两步配置落盘：写 profile 补丁 + Key + 设为默认。"""
    pid = (profile_id or "").strip()
    if not pid:
        return False, "请先选择算力来源。"
    try:
        prof = resolve_profile("text_llm", pid)
    except KeyError:
        return False, "找不到该算力来源。"

    base = (api_base or "").strip() or str(prof.get("api_base") or "").strip()
    mdl = (model or "").strip() or str(prof.get("model") or "").strip()
    if not base or not mdl:
        return False, "缺少服务地址或模型名。"

    is_ollama = "ollama" in pid.lower() or "11434" in base
    key = (api_key or "").strip()
    if not is_ollama and not key:
        # 已有密钥可跳过重填
        from services.integrations.secrets import get_profile_secret, get_secret

        if not (
            get_profile_secret("text_llm", pid, "api_key")
            or (pid == "moonshot_kimi" and get_secret("llm", "api_key"))
        ):
            return False, "请粘贴 API Key。"

    from services.integrations.config import save_integrations_config
    from services.integrations.secrets import set_profile_secret, set_secret
    from services.model_catalog import save_user_profile_patch, set_active_profile_id

    patch: dict = {
        "api_base": base,
        "model": mdl,
        "provider": "openai_compatible",
    }
    save_user_profile_patch("text_llm", pid, patch)
    set_active_profile_id("text_llm", pid)
    if key:
        set_profile_secret("text_llm", pid, "api_key", key)
        if pid == "moonshot_kimi":
            set_secret("llm", "api_key", key)
    save_integrations_config(
        {
            "llm": {
                "enabled": True,
                "provider": "openai_compatible",
                "api_base": base,
                "model": mdl,
                "note": "摘要、改写；多配置见 model_catalog",
            }
        }
    )
    label = str(prof.get("label") or pid)
    return True, f"已保存并设为默认：{label}"


class LlmSimpleSetupDialog(BaseDialog):
    """① 选算力来源 → ② Key（或本机模型名）→ 保存。"""

    dialog_kind = "medium"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("简单配置（两步）")
        self.saved = False
        self.profile_id = ""

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(
            HintLabel(
                "只两步，保存后自动记住。业务页不用填 API 表单。"
                "小白也可稍后再说，不影响浏览页面。"
            )
        )

        lay.addWidget(HintLabel("① 选算力来源"))
        src_row = QHBoxLayout()
        src_row.setSpacing(8)
        self._src_group = QButtonGroup(self)
        self._radios: dict[str, RadioButton] = {}
        catalog_ids = {str(p.get("id") or "") for p in list_profiles("text_llm")}
        first = True
        for pid, label, _kind in _SIMPLE_SOURCES:
            if pid not in catalog_ids:
                continue
            rb = RadioButton(label)
            rb.setProperty("profile_id", pid)
            self._src_group.addButton(rb)
            self._radios[pid] = rb
            src_row.addWidget(rb)
            if first:
                rb.setChecked(True)
                first = False
            rb.toggled.connect(self._on_source_changed)
        src_row.addStretch(1)
        lay.addLayout(src_row)

        self._step2_label = HintLabel("② 粘贴 API Key")
        lay.addWidget(self._step2_label)
        self._key = PasswordLineEdit()
        self._key.setPlaceholderText("sk-…（仅存本机）")
        lay.addWidget(self._key)

        self._model_wrap = QWidget()
        mw = QVBoxLayout(self._model_wrap)
        mw.setContentsMargins(0, 0, 0, 0)
        mw.setSpacing(6)
        mw.addWidget(HintLabel("本机模型名（与 ollama pull 一致）"))
        self._model = LineEdit()
        self._model.setPlaceholderText("例如 llama3.2 / qwen2.5")
        mw.addWidget(self._model)
        lay.addWidget(self._model_wrap)

        self._hint = HintLabel("")
        self._hint.setWordWrap(True)
        lay.addWidget(self._hint)

        btn_row = QHBoxLayout()
        btn_save = PrimaryButton("保存并设为默认")
        btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(btn_save)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        buttons = DialogButtonRow()
        buttons.add_secondary("稍后再说", self.reject)
        lay.addWidget(buttons)

        self._on_source_changed()

    def _selected_pid(self) -> str:
        for pid, rb in self._radios.items():
            if rb.isChecked():
                return pid
        return ""

    def _on_source_changed(self, *_args) -> None:
        pid = self._selected_pid()
        is_ollama = "ollama" in pid
        self._model_wrap.setVisible(is_ollama)
        self._key.setVisible(not is_ollama)
        self._step2_label.setText(
            "② 确认本机模型名（通常不用 Key）" if is_ollama else "② 粘贴 API Key"
        )
        try:
            prof = resolve_profile("text_llm", pid) if pid else {}
        except KeyError:
            prof = {}
        if is_ollama:
            self._model.setText(str(prof.get("model") or "llama3.2"))
            self._hint.setText("请先在本机启动 Ollama；模型名需与已拉取的一致。")
        else:
            self._hint.setText(
                f"将写入本机密钥库，并设「{prof.get('label') or pid}」为默认。"
            )

    def _on_save(self) -> None:
        pid = self._selected_pid()
        is_ollama = "ollama" in pid
        ok, msg = bind_text_llm_simple(
            pid,
            api_key="" if is_ollama else self._key.text().strip(),
            model=self._model.text().strip() if is_ollama else "",
        )
        if not ok:
            show_warning(self, msg)
            return
        self.saved = True
        self.profile_id = pid
        show_success(self, msg)
        self.accept()
