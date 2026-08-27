# -*- coding: utf-8 -*-
"""番茄钟：沉浸专注环（进度可见 · 氛围呼吸 · 番茄趣味）。

对标：Forest（专注可感）、Focus To-Do（干净主路径）、GlassFocus（氛围环）。
独到：壳层沉浸 + 已消耗进度弧 + 今日番茄点阵。
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.app_state import AppState
from core.base_dialog import BaseDialog
from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from core.user_messages import show_warning
from modules.pomodoro.pomodoro_store import (
    add_scenario,
    bump_session_today,
    color_presets,
    delete_scenario,
    get_scenario,
    list_scenarios,
    load_settings,
    resolve_accent_hex,
    set_accent,
    set_active_scenario,
    sessions_today,
    update_scenario,
)
from widgets import (
    ComboBox,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PrimaryButton,
    SecondaryButton,
    SemanticLabel,
    SpinBox,
)
from widgets.dialog_actions import DialogButtonRow
from widgets.list_edit import FormEditDialog, ListPanel, confirm_delete


class _ColorChip(QToolButton):
    picked = Signal(str)

    def __init__(self, chip_id: str, hex_color: str | None, label: str, parent=None) -> None:
        super().__init__(parent)
        self._chip_id = chip_id
        self._hex = hex_color
        self.setCheckable(True)
        self.setToolTip(label)
        self.setFixedSize(26, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(lambda: self.picked.emit(self._chip_id))

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = AppState.get().palette or {}
        if self._chip_id == "theme":
            fill = QColor(str(pal.get("primary") or "#0D9488"))
        elif self._hex:
            fill = QColor(self._hex)
        else:
            fill = QColor(str(pal.get("surface") or "#F3F4F6"))
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(3, 3, self.width() - 6, self.height() - 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawEllipse(rect)
        if self.isChecked():
            pen = QPen(QColor(str(pal.get("text_primary") or "#111827")), 2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(rect.adjusted(-1.5, -1.5, 1.5, 1.5))
        p.end()


class _TomatoRow(QWidget):
    """今日番茄点阵：已完成实心，趣味反馈。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._count = 0
        self._accent = QColor("#E11D48")
        self.setFixedHeight(28)
        self.setMinimumWidth(200)

    def set_count(self, n: int, accent: QColor | None = None) -> None:
        self._count = max(0, int(n))
        if accent is not None and accent.isValid():
            self._accent = QColor(accent)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        slots = max(4, min(8, max(self._count, 4)))
        r = 7.0
        gap = 10.0
        total_w = slots * (r * 2) + (slots - 1) * gap
        x0 = (self.width() - total_w) / 2 + r
        y = self.height() / 2
        empty = QColor(self._accent)
        empty.setAlpha(55)
        for i in range(slots):
            cx = x0 + i * (r * 2 + gap)
            filled = i < self._count
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._accent if filled else empty)
            p.drawEllipse(QPointF(cx, y), r, r)
            if filled:
                leaf = QColor(str((AppState.get().palette or {}).get("success") or "#16A34A"))
                p.setBrush(leaf)
                p.drawEllipse(QPointF(cx + 2, y - r + 1), 2.2, 2.2)
        p.end()


class _PomodoroRing(QWidget):
    """沉浸专注环：轨道 + 已消耗进度弧 + 呼吸光晕 + 相位文案。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(360, 360)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._elapsed = 0.0
        self._label = "25:00"
        self._phase = "准备开始"
        self._sub = "点下方开始，进入专注"
        self._pulse = 0.0
        self._running = False
        self._on_break = False
        self._accent_hex: str | None = None
        self._anim = QTimer(self)
        self._anim.setInterval(33)
        self._anim.timeout.connect(self._tick_pulse)

    def set_accent(self, hex_color: str | None) -> None:
        self._accent_hex = hex_color
        self.update()

    def set_state(
        self,
        *,
        elapsed: float,
        label: str,
        phase: str,
        sub: str,
        running: bool,
        on_break: bool,
    ) -> None:
        self._elapsed = max(0.0, min(1.0, float(elapsed)))
        self._label = label
        self._phase = phase
        self._sub = sub
        self._running = running
        self._on_break = on_break
        if running and not self._anim.isActive():
            self._anim.start()
        if not running and self._anim.isActive():
            self._anim.stop()
            self._pulse = 0.0
        self.update()

    def _tick_pulse(self) -> None:
        self._pulse = (self._pulse + 0.06) % (math.pi * 2)
        self.update()

    def _colors(self) -> tuple[QColor, QColor, QColor, QColor]:
        pal = AppState.get().palette or {}
        if self._accent_hex:
            primary = QColor(self._accent_hex)
        else:
            primary = QColor(str(pal.get("primary") or "#0D9488"))
        if self._on_break:
            primary = QColor(str(pal.get("success") or "#16A34A"))
        track = QColor(str(pal.get("border") or "#E5E7EB"))
        text = QColor(str(pal.get("text_primary") or "#111827"))
        muted = QColor(str(pal.get("text_secondary") or pal.get("text2") or "#6B7280"))
        return primary, track, text, muted

    def paintEvent(self, event) -> None:  # noqa: N802
        primary, track, text, muted = self._colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        cx, cy = self.width() / 2, self.height() / 2
        side = min(self.width(), self.height())
        ring_w = 18.0
        pad = 28.0
        rect = QRectF(pad, pad, side - 2 * pad, side - 2 * pad)

        breath = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self._pulse)) if self._running else 0.35
        glow = QColor(primary)
        glow.setAlpha(int(36 + 40 * breath) if self._running else 22)
        grad = QRadialGradient(QPointF(cx, cy), side * 0.48)
        grad.setColorAt(0.0, glow)
        soft = QColor(primary)
        soft.setAlpha(0)
        grad.setColorAt(1.0, soft)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawEllipse(QPointF(cx, cy), side * 0.48, side * 0.48)

        disc = QColor(primary)
        disc.setAlpha(18 if self._running else 10)
        painter.setBrush(disc)
        painter.drawEllipse(rect.adjusted(14, 14, -14, -14))

        pen_track = QPen(track, ring_w)
        pen_track.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_track)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)

        span = -int(360 * 16 * self._elapsed)
        if abs(span) > 0:
            pen_arc = QPen(primary, ring_w)
            pen_arc.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen_arc)
            painter.drawArc(rect, 90 * 16, span)

            ang = math.radians(90 - 360 * self._elapsed)
            rr = rect.width() / 2
            hx = cx + rr * math.cos(ang)
            hy = cy - rr * math.sin(ang)
            tip = QColor(primary)
            tip.setAlpha(220)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(tip)
            painter.drawEllipse(QPointF(hx, hy), ring_w * 0.42, ring_w * 0.42)
            halo = QColor(primary)
            halo.setAlpha(90)
            painter.setBrush(halo)
            painter.drawEllipse(QPointF(hx, hy), ring_w * 0.75, ring_w * 0.75)

        font = QFont("Segoe UI")
        font.setPixelSize(56)
        font.setBold(True)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        painter.setFont(font)
        painter.setPen(text)
        time_rect = QRectF(rect.left(), cy - 48, rect.width(), 64)
        painter.drawText(
            time_rect,
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            self._label,
        )

        f2 = QFont("Segoe UI")
        f2.setPixelSize(15)
        f2.setBold(True)
        painter.setFont(f2)
        painter.setPen(primary)
        painter.drawText(
            QRectF(rect.left(), cy + 18, rect.width(), 24),
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            self._phase,
        )

        f3 = QFont("Segoe UI")
        f3.setPixelSize(12)
        painter.setFont(f3)
        painter.setPen(muted)
        painter.drawText(
            QRectF(rect.left(), cy + 42, rect.width(), 22),
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            self._sub,
        )
        painter.end()


class _ScenarioManageDialog(BaseDialog):
    dialog_kind = "medium"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("管理场景")
        self._ids: list[str] = []
        lay = QVBoxLayout(self)
        lay.addWidget(HintLabel("内置场景不可删；自定义可增删改。"))
        self._panel = ListPanel(
            add_label="新增",
            edit_label="编辑",
            delete_label="删除",
            show_refresh=False,
            hint="",
        )
        self._panel.bind_add(self._on_add)
        self._panel.bind_edit(self._on_edit)
        self._panel.bind_delete(self._on_delete)
        lay.addWidget(self._panel, 1)
        row = DialogButtonRow()
        row.add_primary("完成", self.accept)
        lay.addWidget(row)
        self._reload()

    def _reload(self) -> None:
        scenes = list_scenarios()
        self._ids = [str(s.get("id") or "") for s in scenes]
        self._panel.set_items(
            [f"{s.get('name')}  ·  {s.get('work_min')}/{s.get('break_min')} 分" for s in scenes]
        )

    def _on_add(self) -> None:
        dlg = FormEditDialog(
            self,
            title="新增场景",
            fields=[("名称", "name"), ("专注(分)", "work"), ("休息(分)", "break")],
            ok_text="添加",
        )
        dlg.set_values({"name": "我的场景", "work": "25", "break": "5"})
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.values()
        try:
            add_scenario(
                str(vals.get("name") or ""),
                int(vals.get("work") or 25),
                int(vals.get("break") or 5),
            )
        except ValueError as exc:
            show_warning(self, str(exc))
            return
        self._reload()

    def _on_edit(self) -> None:
        row = self._panel.current_row()
        if row < 0 or row >= len(self._ids):
            return
        sid = self._ids[row]
        scene = get_scenario(sid)
        if not scene:
            return
        if scene.get("builtin"):
            show_warning(self, "内置场景不可编辑，可用「另存」复制。")
            return
        dlg = FormEditDialog(
            self,
            title="编辑场景",
            fields=[("名称", "name"), ("专注(分)", "work"), ("休息(分)", "break")],
        )
        dlg.set_values(
            {
                "name": scene.get("name"),
                "work": str(scene.get("work_min")),
                "break": str(scene.get("break_min")),
            }
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.values()
        try:
            update_scenario(
                sid,
                name=str(vals.get("name") or ""),
                work_min=int(vals.get("work") or 25),
                break_min=int(vals.get("break") or 5),
            )
        except ValueError as exc:
            show_warning(self, str(exc))
            return
        self._reload()

    def _on_delete(self) -> None:
        row = self._panel.current_row()
        if row < 0 or row >= len(self._ids):
            return
        sid = self._ids[row]
        scene = get_scenario(sid)
        if not scene:
            return
        if scene.get("builtin"):
            show_warning(self, "内置场景不可删除。")
            return
        if not confirm_delete(self, f"「{scene.get('name')}」"):
            return
        try:
            delete_scenario(sid)
        except ValueError as exc:
            show_warning(self, str(exc))
            return
        self._reload()


class _PrefsDialog(BaseDialog):
    dialog_kind = "medium"

    def __init__(
        self,
        parent,
        *,
        work_min: int,
        break_min: int,
        scenario_id: str,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("番茄偏好")
        self._color_chips: dict[str, _ColorChip] = {}
        self.work_min = work_min
        self.break_min = break_min
        self.scenario_id = scenario_id

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 20, 16, 12)
        lay.setSpacing(14)

        dur = FormSection("本轮时长")
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)
        self._spin_work = SpinBox()
        self._spin_work.setRange(1, 120)
        self._spin_work.setValue(work_min)
        self._spin_work.setSuffix(" 分")
        form.addRow("专注", self._spin_work)
        self._spin_break = SpinBox()
        self._spin_break.setRange(1, 60)
        self._spin_break.setValue(break_min)
        self._spin_break.setSuffix(" 分")
        form.addRow("休息", self._spin_break)
        dur.add_layout(form)
        lay.addWidget(dur)

        scene = FormSection("场景")
        srow = QHBoxLayout()
        self._combo = ComboBox()
        for s in list_scenarios():
            self._combo.addItem(str(s.get("name") or ""), str(s.get("id")))
        idx = self._combo.findData(scenario_id)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        self._combo.currentIndexChanged.connect(self._on_scene)
        srow.addWidget(self._combo, 1)
        btn_manage = SecondaryButton("管理")
        btn_manage.clicked.connect(self._manage)
        srow.addWidget(btn_manage)
        btn_save = SecondaryButton("另存")
        btn_save.clicked.connect(self._save_as)
        srow.addWidget(btn_save)
        scene.add_layout(srow)
        lay.addWidget(scene)

        color = FormSection("环颜色")
        crow = QHBoxLayout()
        for chip_id, label, hex_color in color_presets():
            chip = _ColorChip(chip_id, hex_color, label, self)
            chip.picked.connect(self._on_color)
            self._color_chips[chip_id] = chip
            crow.addWidget(chip)
        crow.addStretch(1)
        color.add_layout(crow)
        crow2 = QHBoxLayout()
        self._custom = LineEdit()
        self._custom.setPlaceholderText("#7C3AED")
        crow2.addWidget(self._custom, 1)
        btn_c = SecondaryButton("应用色值")
        btn_c.clicked.connect(self._apply_custom)
        crow2.addWidget(btn_c)
        color.add_layout(crow2)
        lay.addWidget(color)

        row = DialogButtonRow()
        row.add_secondary("取消", self.reject)
        row.add_primary("确定", self.accept)
        lay.addWidget(row)
        self._sync_colors()

    def _on_scene(self, index: int) -> None:
        sid = str(self._combo.itemData(index) or "")
        scene = get_scenario(sid)
        if not scene:
            return
        self.scenario_id = sid
        self._spin_work.setValue(int(scene.get("work_min") or 25))
        self._spin_break.setValue(int(scene.get("break_min") or 5))

    def _manage(self) -> None:
        dlg = _ScenarioManageDialog(self)
        dlg.exec()
        cur = self.scenario_id
        self._combo.blockSignals(True)
        self._combo.clear()
        for s in list_scenarios():
            self._combo.addItem(str(s.get("name") or ""), str(s.get("id")))
        self._combo.blockSignals(False)
        idx = self._combo.findData(cur)
        if idx < 0:
            idx = 0
        self._combo.setCurrentIndex(idx)
        self._on_scene(self._combo.currentIndex())

    def _save_as(self) -> None:
        dlg = FormEditDialog(self, title="另存为场景", fields=[("名称", "name")], ok_text="保存")
        dlg.set_values({"name": "我的场景"})
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name = (dlg.values().get("name") or "").strip()
        if not name:
            show_warning(self, "请填写名称。")
            return
        try:
            entry = add_scenario(name, int(self._spin_work.value()), int(self._spin_break.value()))
        except ValueError as exc:
            show_warning(self, str(exc))
            return
        self.scenario_id = str(entry.get("id"))
        self._combo.blockSignals(True)
        self._combo.clear()
        for s in list_scenarios():
            self._combo.addItem(str(s.get("name") or ""), str(s.get("id")))
        self._combo.blockSignals(False)
        idx = self._combo.findData(self.scenario_id)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)

    def _sync_colors(self) -> None:
        key = str(load_settings().get("accent_key") or "theme")
        custom = str(load_settings().get("custom_accent") or "")
        self._custom.setText(custom if key == "custom" else "")
        for cid, chip in self._color_chips.items():
            chip.blockSignals(True)
            chip.setChecked(cid == key)
            chip.blockSignals(False)

    def _on_color(self, chip_id: str) -> None:
        set_accent(chip_id)
        self._sync_colors()

    def _apply_custom(self) -> None:
        raw = (self._custom.text() or "").strip()
        if not raw.startswith("#") or len(raw) < 4:
            show_warning(self, "请输入如 #7C3AED 的色值。")
            return
        set_accent("custom", custom_hex=raw)
        self._sync_colors()

    def accept(self) -> None:  # noqa: N802
        self.work_min = int(self._spin_work.value())
        self.break_min = int(self._spin_break.value())
        self.scenario_id = str(self._combo.currentData() or self.scenario_id)
        super().accept()


class PomodoroPage(BasePage):
    page_id = "pomodoro"
    page_title = "番茄钟"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        settings = load_settings()
        active = get_scenario(str(settings.get("active_scenario_id") or "standard")) or list_scenarios()[0]
        self._work_min = int(active.get("work_min") or 25)
        self._break_min = int(active.get("break_min") or 5)
        self._seconds_left = self._work_min * 60
        self._total_seconds = self._seconds_left
        self._on_break = False
        self._running = False
        self._sessions = sessions_today()
        self._scenario_id = str(active.get("id") or "standard")

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._entered_immersive = False

        m = page_content_margins()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*m)
        outer.setSpacing(10)

        head = QHBoxLayout()
        head.addWidget(
            PageHeader("番茄钟", "沉浸专注 · 进度环会「吃掉」时间 · 完成后托盘提醒"),
            1,
        )
        self._btn_prefs = SecondaryButton("偏好")
        self._btn_prefs.setToolTip("场景 · 时长 · 配色")
        self._btn_prefs.clicked.connect(self._open_prefs)
        head.addWidget(self._btn_prefs, 0, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(head)

        self._focus_tip = SemanticLabel(
            "专注中进度环会随时间「被吃掉」—— 完成后托盘提醒，场景与配色在「偏好」。",
            kind="success",
        )
        outer.addWidget(self._focus_tip)

        self._chrome = QWidget()
        top = QHBoxLayout(self._chrome)
        top.setContentsMargins(0, 0, 0, 0)
        self._combo_scene = ComboBox()
        self._combo_scene.setMinimumWidth(160)
        self._combo_scene.currentIndexChanged.connect(self._on_scene_changed)
        top.addWidget(HintLabel("场景"))
        top.addWidget(self._combo_scene, 0)
        self._scene_meta = HintLabel("")
        top.addWidget(self._scene_meta, 1)
        outer.addWidget(self._chrome)

        outer.addStretch(1)

        center = QVBoxLayout()
        center.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        center.setSpacing(14)
        self._ring = _PomodoroRing()
        center.addWidget(self._ring, 0, Qt.AlignmentFlag.AlignHCenter)

        self._tomatoes = _TomatoRow()
        center.addWidget(self._tomatoes, 0, Qt.AlignmentFlag.AlignHCenter)

        self._session_hint = HintLabel("")
        self._session_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.addWidget(self._session_hint)
        outer.addLayout(center)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        actions.addStretch(1)
        self._btn_start = PrimaryButton("开始专注")
        self._btn_start.setMinimumWidth(168)
        self._btn_start.setMinimumHeight(40)
        self._btn_start.clicked.connect(self._toggle)
        actions.addWidget(self._btn_start)
        self._btn_reset = SecondaryButton("重置")
        self._btn_reset.setMinimumHeight(40)
        self._btn_reset.clicked.connect(self._reset)
        actions.addWidget(self._btn_reset)
        actions.addStretch(1)
        outer.addLayout(actions)

        outer.addStretch(2)

        self._reload_scenarios(select_id=self._scenario_id)
        self._apply_accent_to_ring()
        self._refresh_ring()
        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        return self._btn_start

    def _reload_scenarios(self, *, select_id: str | None = None) -> None:
        self._combo_scene.blockSignals(True)
        self._combo_scene.clear()
        for s in list_scenarios():
            self._combo_scene.addItem(str(s.get("name") or ""), str(s.get("id")))
        self._combo_scene.blockSignals(False)
        target = select_id or self._scenario_id
        idx = self._combo_scene.findData(target)
        if idx >= 0:
            self._combo_scene.setCurrentIndex(idx)
        self._update_scene_meta()

    def _update_scene_meta(self) -> None:
        scene = get_scenario(self._scenario_id)
        if not scene:
            self._scene_meta.setText("")
            return
        self._scene_meta.setText(
            f"{scene.get('work_min')} 分专注 · {scene.get('break_min')} 分休息"
        )

    def _apply_durations(self, work: int, brk: int, *, reset_clock: bool) -> None:
        self._work_min = work
        self._break_min = brk
        if reset_clock and not self._running:
            self._on_break = False
            self._seconds_left = self._work_min * 60
            self._total_seconds = self._seconds_left
            self._btn_start.setText("开始专注")

    def _on_scene_changed(self, index: int) -> None:
        if index < 0:
            return
        sid = str(self._combo_scene.itemData(index) or "")
        scene = get_scenario(sid)
        if scene is None:
            return
        self._scenario_id = sid
        set_active_scenario(sid)
        self._apply_durations(
            int(scene.get("work_min") or 25),
            int(scene.get("break_min") or 5),
            reset_clock=True,
        )
        self._update_scene_meta()
        self._refresh_ring()

    def _open_prefs(self) -> None:
        if self._running:
            show_warning(self, "计时中请先暂停或重置，再改偏好。")
            return
        dlg = _PrefsDialog(
            self,
            work_min=self._work_min,
            break_min=self._break_min,
            scenario_id=self._scenario_id,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            self._apply_accent_to_ring()
            return
        self._scenario_id = dlg.scenario_id
        set_active_scenario(self._scenario_id)
        self._apply_durations(dlg.work_min, dlg.break_min, reset_clock=True)
        self._reload_scenarios(select_id=self._scenario_id)
        self._apply_accent_to_ring()
        self._refresh_ring()
        self.report_status("偏好已更新", level=StatusLevel.SUCCESS)

    def _apply_accent_to_ring(self) -> None:
        hex_c = resolve_accent_hex()
        self._ring.set_accent(hex_c)
        tomato = QColor("#E11D48") if not self._on_break else QColor(
            str((AppState.get().palette or {}).get("success") or "#16A34A")
        )
        self._tomatoes.set_count(self._sessions, tomato)

    def _fmt(self, sec: int) -> str:
        sec = max(0, int(sec))
        return f"{sec // 60:02d}:{sec % 60:02d}"

    def _phase_copy(self) -> tuple[str, str]:
        scene = get_scenario(self._scenario_id)
        name = str(scene.get("name") if scene else "") or "专注"
        total = max(1, self._total_seconds)
        elapsed_pct = int(round(100 * (1.0 - self._seconds_left / total)))
        if self._running and self._on_break:
            return "休息中", f"放松一下 · 已过 {elapsed_pct}%"
        if self._running:
            return f"专注中 · {name}", f"已消耗 {elapsed_pct}% · 沉浸前进"
        if self._on_break and self._btn_start.text().startswith("开始休息"):
            return "专注完成", "收获一枚番茄 · 可以开始休息"
        if self._btn_start.text() == "继续":
            return "已暂停", f"进度保留在 {elapsed_pct}% · 随时继续"
        return "准备开始", "点下方开始，环会吞掉时间"

    def _refresh_ring(self) -> None:
        total = max(1, self._total_seconds)
        elapsed = 1.0 - (self._seconds_left / total)
        phase, sub = self._phase_copy()
        self._ring.set_state(
            elapsed=elapsed,
            label=self._fmt(self._seconds_left),
            phase=phase,
            sub=sub,
            running=self._running,
            on_break=self._on_break,
        )
        self._session_hint.setText(
            f"今日已种下 {self._sessions} 枚番茄"
            if self._sessions
            else "今日还没有番茄 · 完成一轮即可点亮"
        )
        self._apply_accent_to_ring()
        self._combo_scene.setEnabled(not self._running)
        self._btn_prefs.setEnabled(not self._running)
        self._chrome.setVisible(not self._running)

    def _set_focus_immersive(self, on: bool) -> None:
        win = self.window()
        if win is None or not hasattr(win, "set_immersive"):
            return
        if on:
            if hasattr(win, "is_immersive") and win.is_immersive():
                self._entered_immersive = True
                return
            win.set_immersive(True)
            self._entered_immersive = True
            return
        if self._entered_immersive:
            win.set_immersive(False)
            self._entered_immersive = False

    def _toggle(self) -> None:
        if self._running:
            self._timer.stop()
            self._running = False
            self._btn_start.setText("继续")
            self._set_focus_immersive(False)
            self._refresh_ring()
            self.report_status("已暂停 · 进度保留", level=StatusLevel.WARNING)
            return
        if self._seconds_left <= 0:
            self._seconds_left = self._work_min * 60
            self._total_seconds = self._seconds_left
        self._running = True
        self._btn_start.setText("暂停")
        self._timer.start()
        if not self._on_break:
            self._set_focus_immersive(True)
        self._refresh_ring()
        self.report_status("专注开始 · Esc 可退出沉浸", level=StatusLevel.INFO)

    def _reset(self) -> None:
        self._timer.stop()
        self._running = False
        self._on_break = False
        self._seconds_left = self._work_min * 60
        self._total_seconds = self._seconds_left
        self._btn_start.setText("开始专注")
        self._set_focus_immersive(False)
        self._refresh_ring()
        self.report_status("已重置", level=StatusLevel.INFO)

    def _tick(self) -> None:
        self._seconds_left -= 1
        self._refresh_ring()
        self.report_status(f"番茄钟 {self._fmt(self._seconds_left)}")
        if self._seconds_left > 0:
            return
        self._timer.stop()
        self._running = False
        self._set_focus_immersive(False)
        from services.notify_bus import NotifyLevel, notify

        if not self._on_break:
            self._sessions = bump_session_today()
            self._on_break = True
            self._seconds_left = self._break_min * 60
            self._total_seconds = self._seconds_left
            self._btn_start.setText("开始休息")
            notify(
                NotifyLevel.SUCCESS,
                title="番茄钟",
                body="专注完成，收获一枚番茄。休息一下吧。",
                channel="all",
                parent=self,
            )
            self.report_status("专注完成 · 番茄 +1", level=StatusLevel.SUCCESS)
        else:
            self._on_break = False
            self._seconds_left = self._work_min * 60
            self._total_seconds = self._seconds_left
            self._btn_start.setText("开始专注")
            notify(
                NotifyLevel.INFO,
                title="番茄钟",
                body="休息结束，可以开始下一轮专注。",
                channel="all",
                parent=self,
            )
            self.report_status("休息结束 · 准备下一轮", level=StatusLevel.INFO)
        self._refresh_ring()

    def on_enter(self) -> None:
        self._sessions = sessions_today()
        self._apply_accent_to_ring()
        self._refresh_ring()
        self.report_status("番茄钟 · 开始后自动沉浸")

    def on_leave(self) -> None:
        self._set_focus_immersive(False)

    def on_theme_changed(self, _theme_id: str, _palette: dict) -> None:
        if str(load_settings().get("accent_key") or "theme") == "theme":
            self._apply_accent_to_ring()
        self._refresh_ring()
