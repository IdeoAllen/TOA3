# -*- coding: utf-8 -*-
"""Hub 内本地 Web Host：严格继承 Comfy=`LocalWebHostPage`，扩展六件套入口。"""
from __future__ import annotations

from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl

from core.status_service import StatusLevel
from core.user_messages import ask_confirm, show_info, show_saved, show_warning
from modules.local_web_host.local_web_host_page import LocalWebHostPage
from services.local_web_engine import get_spec


class HubLocalWebHost(LocalWebHostPage):
    """详情区与 comfyui_web / open_pencil 同构；page_id 固定为管家，供壳层校验。"""

    page_id = "engine_host_hub"
    page_title = "引擎管家"
    engine_id = ""

    def __init__(self, engine_id: str, parent=None) -> None:
        eid = str(engine_id or "").strip()
        self.engine_id = eid
        self.page_id = "engine_host_hub"
        spec = get_spec(eid)
        self.page_title = (spec.title if spec else None) or eid
        super().__init__(parent)
        # 六件套扩展（不改基类；仅管家子类菜单多几项）
        self._more_menu.addSeparator()
        self._more_menu.addAction("打开日志", self._hub_open_logs)
        self._more_menu.addAction("一键修复", self._hub_repair)
        self._more_menu.addAction("版本备份", self._hub_backup)
        self._more_menu.addAction("一键卸载…", self._hub_uninstall)

    def _hub_open_logs(self) -> None:
        from services.engine_host.lifecycle import open_log

        ok, msg, path = open_log(self.engine_id)
        if not ok or path is None:
            show_warning(self, msg or "无法打开日志")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        if path.is_file():
            show_saved(self, "已打开日志", path)
        else:
            show_info(self, msg)
        self.report_status(msg, level=StatusLevel.INFO)

    def _hub_repair(self) -> None:
        from services.engine_host.lifecycle import repair_engine

        self.report_status("正在修复…", level=StatusLevel.INFO)
        ok, msg = repair_engine(self.engine_id)
        if ok:
            show_info(self, msg or "修复完成")
            self.report_status("修复完成", level=StatusLevel.SUCCESS)
            self._refresh_status(force=True)
        else:
            show_warning(self, msg or "修复失败")
            self.report_status(msg or "修复失败", level=StatusLevel.WARNING)

    def _hub_backup(self) -> None:
        from services.engine_host.lifecycle import backup_engine

        self.report_status("正在备份（可能较慢）…", level=StatusLevel.INFO)
        ok, msg, path = backup_engine(self.engine_id)
        if ok and path is not None:
            show_saved(self, msg, path)
            self.report_status("备份完成", level=StatusLevel.SUCCESS)
        else:
            show_warning(self, msg or "备份失败")

    def _hub_uninstall(self) -> None:
        from services.engine_host.lifecycle import uninstall_engine

        if not ask_confirm(
            self,
            f"卸载「{self.page_title}」？\n将停止进程并清除本机目录登记。",
            title="一键卸载",
        ):
            return
        delete_files = ask_confirm(
            self,
            "是否同时删除安装目录文件？\n选「否」仅清除登记并停止（推荐先试）。",
            title="删除安装文件",
        )
        ok, msg = uninstall_engine(self.engine_id, delete_files=delete_files)
        if ok:
            show_info(self, msg)
            self.report_status(msg, level=StatusLevel.SUCCESS)
            self._set_detecting_ui(True)
            self._refresh_status(force=True)
        else:
            show_warning(self, msg)
