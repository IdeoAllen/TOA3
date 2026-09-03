# -*- coding: utf-8 -*-
"""draw.io / diagrams.net 原版 Web（本机静态托管）。"""
from modules.local_web_host.local_web_host_page import LocalWebHostPage


class DrawioWebPage(LocalWebHostPage):
    page_id = "drawio_web"
    page_title = "Draw.io 绘图"
    engine_id = "drawio_web"
