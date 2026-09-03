# -*- coding: utf-8 -*-
"""ComfyUI 原版 Web（大成哥-2 · 8189；与媒体工坊 API 并存）。"""
from modules.local_web_host.local_web_host_page import LocalWebHostPage


class ComfyUiWebPage(LocalWebHostPage):
    page_id = "comfyui_web"
    page_title = "ComfyUI（大成哥-2）"
    engine_id = "comfyui_web"
