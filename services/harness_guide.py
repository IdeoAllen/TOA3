# -*- coding: utf-8 -*-
"""Harness 内置说明：TOA 壳层 vs 正版 Web · 小白三步。"""
from __future__ import annotations

NODE_DOWNLOAD_URL = "https://nodejs.org/zh-cn/download"

PRODUCT_POSITION = (
    "中间为 DeepSeek Harness 原版界面。"
    "日常请在「编码智能体」页走三步开用；路径/端口仅高级用户改。"
)

GUIDE_INTRO = (
    "最多三步即可开用：① 安装环境 → ② 粘贴 API Key → ③ 自动启动。"
    "装好后在套件内直接聊天，无需另开浏览器或终端。"
)

STEP_HINTS: dict[str, str] = {
    "runtime": (
        "点「一键安装」：自动准备 Node 组件与 DeepSeek Harness，"
        "数据放在本机独立目录，不干扰其它软件。"
    ),
    "runtime_need_node": (
        "本机还没有 Node.js（运行环境）。请先安装官方 LTS（18 及以上），"
        "装完后回到本页点重试——仍然只需这一步，不必手填路径。"
    ),
    "credentials": (
        "环境已就绪。粘贴 DeepSeek API Key 后点「保存并启动」。"
        "密钥只写在本机，不会上传到 TOA 服务器。"
    ),
    "start": (
        "正在启动并打开内嵌界面。之后聊天、改文件、装插件都在中间页面完成。"
    ),
}

FAQ_LINES: list[str] = [
    "Q：和单独打开 Harness / 浏览器一样吗？\nA：是同一套官方界面；TOA 只是嵌进办公套件，并接上剪贴板/截图投喂。",
    "Q：为什么不要我填一堆路径？\nA：小白主路径自动安装到独立目录；只有高级用户才去系统设置改路径。",
    "Q：以前装过其它带 Harness 的软件会冲突吗？\nA：TOA 会自动用自己的目录与端口，并在需要时帮你迁开冲突配置。",
    "Q：工作区、插件在哪配？\nA：启动后在 Harness 页面左侧栏与设置里，与官方用法相同。",
    "Q：办公链「送到智能体」？\nA：从剪贴板/截图送入本页后，在 Harness 输入框粘贴或按页内提示继续。",
]
