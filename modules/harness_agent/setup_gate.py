# -*- coding: utf-8 -*-
"""未安装 / 待配置时的主区引导（四步主路径）。

选版本 → 可预期等待 → 配置一次 API Key → 检测通过后启动。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from core.user_messages import show_info, show_warning
from services.harness_credentials import save_api_key
from services.harness_guide import GUIDE_INTRO, NODE_DOWNLOAD_URL, STEP_HINTS
from services.harness_prefab import (
    FLAVOR_BLURBS,
    FLAVOR_LABELS,
    FLAVOR_OFFICIAL,
    FLAVOR_PREFAB,
    bundle_spec,
)
from services.harness_probe import HarnessPageState
from services.harness_setup import NEED_NODE_PREFIX
from widgets import (
    FormSection,
    HintLabel,
    PasswordLineEdit,
    PrimaryButton,
    ProgressBar,
    SecondaryButton,
    SemanticLabel,
)


class SetupGate(QWidget):
    """覆盖主内容区：未就绪时显示四步进度，就绪后隐藏。"""

    install_requested = Signal(str)  # flavor: official | prefab
    cancel_install_requested = Signal()
    key_saved = Signal()
    open_settings_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)

        card = FormSection("编码智能体 · 四步开用")
        card_inner = QVBoxLayout()
        card_inner.setSpacing(10)

        self._intro = HintLabel(GUIDE_INTRO)
        self._intro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._intro.setWordWrap(True)
        card_inner.addWidget(self._intro)

        steps = QHBoxLayout()
        steps.setSpacing(8)
        self._step_labels: list[SemanticLabel] = []
        for text in ("选择版本", "安装等待", "填写密钥", "检测启动"):
            lab = SemanticLabel(text, "info")
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._step_labels.append(lab)
            steps.addWidget(lab, 1)
        card_inner.addLayout(steps)

        self._body = HintLabel("")
        self._body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body.setWordWrap(True)
        card_inner.addWidget(self._body)

        # --- 选版本：两张等权卡片 ---
        self._flavor_row = QWidget()
        flavor_lay = QHBoxLayout(self._flavor_row)
        flavor_lay.setContentsMargins(0, 0, 0, 0)
        flavor_lay.setSpacing(12)

        self._btn_official = PrimaryButton("安装官方版")
        self._btn_official.setToolTip(FLAVOR_BLURBS[FLAVOR_OFFICIAL])
        self._btn_official.clicked.connect(lambda: self.install_requested.emit(FLAVOR_OFFICIAL))
        flavor_lay.addWidget(self._btn_official, 1)

        self._btn_prefab = PrimaryButton("安装预制版")
        self._btn_prefab.setToolTip(FLAVOR_BLURBS[FLAVOR_PREFAB])
        self._btn_prefab.clicked.connect(lambda: self.install_requested.emit(FLAVOR_PREFAB))
        flavor_lay.addWidget(self._btn_prefab, 1)

        card_inner.addWidget(self._flavor_row)

        self._flavor_hints = HintLabel(self._flavor_hint_text())
        self._flavor_hints.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._flavor_hints.setWordWrap(True)
        card_inner.addWidget(self._flavor_hints)

        # --- 安装进度 ---
        self._progress = ProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.hide()
        card_inner.addWidget(self._progress)

        self._progress_label = HintLabel("")
        self._progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_label.setWordWrap(True)
        self._progress_label.hide()
        card_inner.addWidget(self._progress_label)

        # --- Key ---
        self._key_row = QWidget()
        key_lay = QHBoxLayout(self._key_row)
        key_lay.setContentsMargins(0, 0, 0, 0)
        self._key_edit = PasswordLineEdit()
        self._key_edit.setPlaceholderText("粘贴 DeepSeek API Key（仅存本机）")
        key_lay.addWidget(self._key_edit, 1)
        self._btn_key = PrimaryButton("保存并启动")
        self._btn_key.clicked.connect(self._save_key)
        key_lay.addWidget(self._btn_key)
        self._key_row.hide()
        card_inner.addWidget(self._key_row)

        # --- 底部操作 ---
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._btn_cancel = SecondaryButton("取消")
        self._btn_cancel.clicked.connect(self.cancel_install_requested.emit)
        self._btn_cancel.hide()
        btn_row.addWidget(self._btn_cancel)
        self._btn_retry = SecondaryButton("重试")
        self._btn_retry.clicked.connect(self._on_retry)
        self._btn_retry.hide()
        btn_row.addWidget(self._btn_retry)
        self._btn_switch = SecondaryButton("改装另一版本")
        self._btn_switch.clicked.connect(self._on_switch_flavor)
        self._btn_switch.hide()
        btn_row.addWidget(self._btn_switch)
        self._btn_node = SecondaryButton("去安装 Node.js")
        self._btn_node.clicked.connect(self._open_node_download)
        self._btn_node.hide()
        btn_row.addWidget(self._btn_node)
        self._btn_secondary = SecondaryButton("环境维护…")
        self._btn_secondary.clicked.connect(self.open_settings_requested.emit)
        btn_row.addWidget(self._btn_secondary)
        btn_row.addStretch(1)
        card_inner.addLayout(btn_row)

        self._footer = HintLabel("日常请选版本安装；密钥与修复请用「环境维护」。")
        self._footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._footer.setWordWrap(True)
        card_inner.addWidget(self._footer)

        card.add_layout(card_inner)
        outer.addWidget(card)
        outer.addStretch(2)

        self._state = HarnessPageState.CHECKING
        self._need_node = False
        self._last_flavor = FLAVOR_PREFAB
        self._installing = False

    def _flavor_hint_text(self) -> str:
        lines: list[str] = []
        for flavor in (FLAVOR_OFFICIAL, FLAVOR_PREFAB):
            spec = bundle_spec(flavor)
            size = spec.get("size_hint_mb")
            size_s = f"约 {size} MB" if size else "体积见下载页"
            lines.append(
                f"{FLAVOR_LABELS[flavor]}：{FLAVOR_BLURBS[flavor]} · {size_s}"
            )
        return "\n".join(lines)

    def show_state(self, state: HarnessPageState, message: str = "") -> None:
        self._state = state
        self._need_node = False
        if self._installing and state == HarnessPageState.NOT_INSTALLED:
            # 安装中勿被探测刷回选版本
            return

        if state == HarnessPageState.CHECKING:
            self.show()
            self._set_active_step(0)
            self._body.setText(message or "正在确认本机环境…")
            self._hide_install_chrome()
            self._flavor_row.hide()
            self._flavor_hints.hide()
            self._key_row.hide()
            self._btn_secondary.hide()
            self._btn_node.hide()
            self._btn_retry.hide()
            self._btn_switch.hide()
            self._btn_cancel.hide()
            return

        if state == HarnessPageState.NOT_INSTALLED:
            self.show()
            self._set_active_step(1)
            msg = (message or "").strip()
            if msg.startswith(NEED_NODE_PREFIX):
                self._need_node = True
                self._body.setText(
                    msg[len(NEED_NODE_PREFIX) :].strip()
                    or STEP_HINTS["runtime_need_node"]
                )
                self._btn_node.show()
            else:
                self._body.setText(msg or STEP_HINTS["runtime"])
                self._btn_node.hide()
            self._show_choose_flavor()
            return

        if state == HarnessPageState.NEEDS_KEY:
            self.show()
            self._installing = False
            self._set_active_step(3)
            self._body.setText(message or STEP_HINTS["credentials"])
            self._hide_install_chrome()
            self._flavor_row.hide()
            self._flavor_hints.hide()
            self._btn_cancel.hide()
            self._btn_retry.hide()
            self._btn_switch.hide()
            self._btn_node.hide()
            self._btn_secondary.show()
            self._key_row.show()
            self._key_edit.setFocus()
            return

        self.hide()

    def _show_choose_flavor(self) -> None:
        self._installing = False
        self._hide_install_chrome()
        self._flavor_hints.setText(self._flavor_hint_text())
        self._flavor_row.show()
        self._flavor_hints.show()
        self._btn_official.setEnabled(True)
        self._btn_prefab.setEnabled(True)
        self._key_row.hide()
        self._btn_secondary.show()
        self._btn_cancel.hide()
        self._btn_retry.hide()
        self._btn_switch.hide()

    def _hide_install_chrome(self) -> None:
        self._progress.hide()
        self._progress_label.hide()
        self._progress.setValue(0)

    def set_installing(self, active: bool, *, flavor: str = "") -> None:
        if active:
            self._installing = True
            if flavor:
                self._last_flavor = flavor
            label = FLAVOR_LABELS.get(self._last_flavor, "运行环境")
            self._set_active_step(2)
            self._body.setText(
                f"正在安装{label}…体积较大，请稍候；可随时取消。"
            )
            self._flavor_row.hide()
            self._flavor_hints.hide()
            self._key_row.hide()
            self._btn_node.hide()
            self._btn_retry.hide()
            self._btn_switch.hide()
            self._btn_secondary.hide()
            self._btn_cancel.show()
            self._btn_cancel.setEnabled(True)
            self._progress.show()
            self._progress.setValue(0)
            self._progress_label.show()
            self._progress_label.setText("准备中…")
        else:
            self._installing = False
            self._btn_cancel.hide()

    def set_install_progress(self, msg: str, pct: int, stage: str = "") -> None:
        self._installing = True
        self._set_active_step(2)
        self._progress.show()
        self._progress_label.show()
        self._progress.setValue(max(0, min(100, int(pct))))
        detail = msg or stage or "安装中…"
        self._progress_label.setText(f"{int(pct)}% · {detail}")
        self._body.setText(detail)
        self._flavor_row.hide()
        self._flavor_hints.hide()
        self._btn_cancel.show()

    def show_install_failed(self, detail: str, *, flavor: str = "") -> None:
        self._installing = False
        if flavor:
            self._last_flavor = flavor
        self._set_active_step(2)
        self._body.setText(detail or "安装失败，请重试或改装另一版本。")
        self._hide_install_chrome()
        self._flavor_row.hide()
        self._flavor_hints.hide()
        self._key_row.hide()
        self._btn_cancel.hide()
        self._btn_retry.show()
        self._btn_switch.show()
        self._btn_secondary.show()
        if "Node" in (detail or "") or detail.startswith(NEED_NODE_PREFIX):
            self._btn_node.show()
        else:
            self._btn_node.hide()

    def mark_need_node(self, detail: str = "") -> None:
        """兼容旧调用：缺 Node 时回到选版本并显示 Node 引导。"""
        self._need_node = True
        self._installing = False
        self._set_active_step(1)
        self._body.setText(detail or STEP_HINTS["runtime_need_node"])
        self._show_choose_flavor()
        self._btn_node.show()

    def _set_active_step(self, step: int) -> None:
        """step: 0=检测, 1..4=四步高亮。"""
        for i, lab in enumerate(self._step_labels, start=1):
            if step <= 0:
                kind = "info"
            elif i < step:
                kind = "success"
            elif i == step:
                kind = "info"
            else:
                kind = "info"
            lab.setProperty("class", f"semantic-{kind}")
            st = lab.style()
            if st is not None:
                st.unpolish(lab)
                st.polish(lab)
            lab.update()

    def _on_retry(self) -> None:
        self.install_requested.emit(self._last_flavor)

    def _on_switch_flavor(self) -> None:
        other = FLAVOR_OFFICIAL if self._last_flavor == FLAVOR_PREFAB else FLAVOR_PREFAB
        self._last_flavor = other
        self._body.setText(STEP_HINTS["runtime"])
        self._show_choose_flavor()
        self._btn_node.hide()

    def _open_node_download(self) -> None:
        QDesktopServices.openUrl(QUrl(NODE_DOWNLOAD_URL))
        self._body.setText(
            "已打开 Node.js 下载页。装完 LTS 后可再点「安装官方版/预制版」。"
            "若仍无法安装，请到「环境维护」点「修一下」或联系管理员。"
        )

    def _save_key(self) -> None:
        ok, msg = save_api_key(self._key_edit.text())
        if ok:
            self._key_edit.clear()
            self._set_active_step(4)
            self._body.setText(STEP_HINTS["start"])
            show_info(self, "密钥已保存，正在检测并启动…")
            self.key_saved.emit()
        else:
            show_warning(self, msg)
