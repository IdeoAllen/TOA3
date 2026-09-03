# -*- coding: utf-8 -*-
"""引擎扩展包通用页：engine_id = 菜单 module_id。"""
from __future__ import annotations

from modules.local_web_host.local_web_host_page import LocalWebHostPage
from services.local_web_engine import get_spec


class EnginePackPage(LocalWebHostPage):
    """由 module_loader 按菜单 id 注入 engine_id / page_id。"""

    page_id = "engine_pack"
    page_title = "引擎扩展"
    engine_id = ""

    def __init__(self, parent=None, *, engine_id: str = "") -> None:
        eid = str(engine_id or "").strip()
        if eid:
            self.engine_id = eid
            self.page_id = eid
            spec = get_spec(eid)
            if spec is not None:
                self.page_title = spec.title or eid
        super().__init__(parent)


def make_engine_pack_page(engine_id: str) -> EnginePackPage:
    return EnginePackPage(engine_id=engine_id)
