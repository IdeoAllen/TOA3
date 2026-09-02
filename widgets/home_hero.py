# -*- coding: utf-8 -*-
"""首页 Hero：品牌冲击力首屏（仅 objectName + QSS，禁止业务页 setStyleSheet）。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from widgets.buttons import PrimaryButton, SecondaryButton


class HomeHeroBand(QFrame):
    """深色品牌带：Logo · 品牌名 · 标语 · 愿景句 · 主行动。"""

    start_work = Signal()
    search_work = Signal()

    def __init__(
        self,
        *,
        brand: str,
        tagline: str,
        statement: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("HomeHeroBand")
        self.setProperty("class", "home-hero")

        root = QHBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(24)

        logo = QLabel()
        logo.setObjectName("HomeHeroLogo")
        logo.setFixedSize(72, 72)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = self._brand_pixmap(64)
        if not pix.isNull():
            logo.setPixmap(pix)
        root.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(8)
        col.setContentsMargins(0, 0, 0, 0)

        brand_lbl = QLabel(brand)
        brand_lbl.setObjectName("HomeHeroBrand")
        brand_lbl.setWordWrap(True)
        col.addWidget(brand_lbl)

        if tagline:
            tag = QLabel(tagline)
            tag.setObjectName("HomeHeroTagline")
            tag.setWordWrap(True)
            col.addWidget(tag)

        if statement:
            stmt = QLabel(statement)
            stmt.setObjectName("HomeHeroStatement")
            stmt.setWordWrap(True)
            col.addWidget(stmt)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.setContentsMargins(0, 8, 0, 0)
        btn_start = PrimaryButton("一键开工")
        btn_start.setObjectName("HomeHeroPrimary")
        btn_start.clicked.connect(self.start_work.emit)
        btn_search = SecondaryButton("检索工作  Ctrl+K")
        btn_search.setObjectName("HomeHeroSecondary")
        btn_search.clicked.connect(self.search_work.emit)
        actions.addWidget(btn_start, 0)
        actions.addWidget(btn_search, 0)
        actions.addStretch(1)
        col.addLayout(actions)
        col.addStretch(1)

        root.addLayout(col, 1)

    @staticmethod
    def _brand_pixmap(logical: int) -> QPixmap:
        try:
            from PySide6.QtGui import QGuiApplication
            from services.app_branding import resolve_app_icon_png, resolve_brand_logo_png

            path = None
            for resolver in (resolve_brand_logo_png, resolve_app_icon_png):
                candidate = resolver()
                if candidate is not None and candidate.is_file():
                    path = candidate
                    break
            if path is None:
                return QPixmap()
            screen = QGuiApplication.primaryScreen()
            dpr = float(screen.devicePixelRatio()) if screen is not None else 1.0
            src = QPixmap(str(path))
            if src.isNull():
                return QPixmap()
            target = max(1, int(logical * dpr))
            out = src.scaled(
                target,
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            out.setDevicePixelRatio(dpr)
            return out
        except Exception:
            return QPixmap()


class HomeSectionLabel(QWidget):
    """首页分区标题（眉题 + 主标题）。"""

    def __init__(self, text: str, *, eyebrow: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("HomeSectionHead")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 4)
        lay.setSpacing(2)
        if eyebrow:
            eye = QLabel(eyebrow)
            eye.setObjectName("HomeSectionEyebrow")
            lay.addWidget(eye)
        title = QLabel(text)
        title.setObjectName("HomeSectionTitle")
        title.setWordWrap(True)
        lay.addWidget(title)


class HomePromiseStrip(QFrame):
    """承诺要点横条。"""

    def __init__(self, lines: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("HomePromiseStrip")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        for i, line in enumerate(lines[:4]):
            chip = QLabel(line)
            chip.setObjectName("HomePromiseChip")
            chip.setWordWrap(True)
            chip.setProperty("class", "home-promise-chip")
            lay.addWidget(chip, 1)
            if i < min(3, len(lines) - 1):
                sep = QWidget()
                sep.setObjectName("HomePromiseSep")
                sep.setFixedWidth(1)
                sep.setMinimumHeight(36)
                lay.addWidget(sep, 0)
