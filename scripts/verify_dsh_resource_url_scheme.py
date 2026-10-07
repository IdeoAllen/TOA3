# -*- coding: utf-8 -*-
"""Harness 侧栏文件预览：dsh-resource URL 在 Qt WebEngine 中须能解析 hostname=file。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from services.qt_webengine_bootstrap import register_dsh_resource_url_scheme

    if not register_dsh_resource_url_scheme():
        print("FAIL: 无法注册 dsh-resource scheme")
        return 1

    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineWidgets import QWebEngineView

    app = QApplication.instance() or QApplication([])
    view = QWebEngineView()
    errors: list[str] = []
    done = {"ok": False}

    js = r"""
    (function () {
      var u = new URL('dsh-resource://file/session/abc/SKILL.md');
      return JSON.stringify({
        protocol: u.protocol,
        hostname: u.hostname,
        pathname: u.pathname,
        host: u.host
      });
    })()
    """

    def on_result(raw) -> None:
        try:
            if isinstance(raw, dict):
                data = raw
            else:
                data = json.loads(str(raw or "{}"))
        except Exception as exc:
            errors.append(f"无法解析回调: {raw!r} ({exc})")
            app.quit()
            return
        print("parse=", data)
        if data.get("hostname") != "file":
            errors.append(f"hostname 应为 file，实际 {data.get('hostname')!r}")
        path = str(data.get("pathname") or "")
        if not path.startswith("/session/"):
            errors.append(f"pathname 异常: {path!r}")
        done["ok"] = not errors
        app.quit()

    def after_load(ok: bool) -> None:
        if not ok:
            errors.append("setHtml loadFinished=false")
            app.quit()
            return
        view.page().runJavaScript(js, on_result)

    view.loadFinished.connect(after_load)
    view.setHtml("<!DOCTYPE html><html><body>probe</body></html>", QUrl("http://127.0.0.1/"))
    QTimer.singleShot(10000, app.quit)
    app.exec()

    if not done["ok"] and not errors:
        errors.append("JS 回调超时或未完成")
    if errors:
        print("FAIL:")
        for e in errors:
            print(" -", e)
        return 1
    print("VERIFY dsh_resource_url_scheme OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
