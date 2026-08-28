# -*- coding: utf-8 -*-
"""Harness 内置说明：TOA 壳层 vs 正版 Web。"""
from __future__ import annotations

PRODUCT_POSITION = "中间为 Harness 原版界面；会话与工作区在 Harness 内操作。"

GUIDE_INTRO = (
    "首次使用：在下方完成「装运行组件 + 填密钥 + 启动」。"
    "工作区、插件、用量请在启动后的 Harness 页面左侧栏与设置里操作（与独立使用 Harness 相同）。"
)

STEP_HINTS: dict[str, str] = {
    "runtime": (
        "安装 Node 与 dsh 启动器（正版 @deepseek-ai/dsh）。\n"
        "可自动检测本机 WorkBuddy 环境，或一键安装到用户目录。"
    ),
    "credentials": (
        "DeepSeek API Key 写入本机 DSH 配置（与 Harness 官方一致）。\n"
        "不会上传到 TOA 服务器。"
    ),
    "start": (
        "启动后中间加载 Harness 原版页面。\n"
        "聊天、改文件、装插件 — 全部在 Harness Web 里完成。"
    ),
}

FAQ_LINES: list[str] = [
    "Q：TOA 里的 Harness 和浏览器打开一样吗？\nA：是同一套 dsh Web，TOA 只是嵌进办公套件并接上剪贴板/截图链。",
    "Q：工作区、插件在哪配？\nA：在 Harness 页面左侧栏与设置里，不要指望 TOA 另做一套。",
    "Q：左/右小栏是什么？\nA：只读快捷信息（会话索引、token 摘要），完整功能仍在 Harness 内。",
    "Q：办公链「送到智能体」？\nA：复制内容到剪贴板并打开本页，在 Harness 输入框粘贴即可。",
]
