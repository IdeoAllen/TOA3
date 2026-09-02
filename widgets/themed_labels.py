# -*- coding: utf-8 -*-
"""标准标签控件（业务页复用）。"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel


class PageTitle(QLabel):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setProperty("class", "page-title")


class SectionTitle(QLabel):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setProperty("class", "section-title")


class HintLabel(QLabel):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setProperty("class", "hint")
        self.setWordWrap(True)


class SemanticLabel(QLabel):
    """语义色条：success / warning / danger / info。compact=窄行内徽章；score=大号得分/扣分数字。"""

    def __init__(
        self,
        text: str = "",
        kind: str = "info",
        parent=None,
        *,
        compact: bool = False,
        score: bool = False,
    ) -> None:
        super().__init__(text, parent)
        self.setProperty("class", f"semantic-{kind}")
        if compact:
            self.setProperty("compact", "true")
        if score:
            self.setProperty("score", "true")
        self.setWordWrap(not compact and not score)
        st = self.style()
        if st is not None:
            st.unpolish(self)
            st.polish(self)
