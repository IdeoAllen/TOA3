# -*- coding: utf-8 -*-
"""TOA3 更新 manifest 的人类可读 HTML 视图（浏览器直达默认格式化 JSON）。"""
from __future__ import annotations

import html
import json
from typing import Any


def render_manifest_html(
    data: dict[str, Any],
    *,
    product: str,
    channel: str,
    json_url: str,
) -> str:
    pretty = json.dumps(data, ensure_ascii=False, indent=2)
    version = str(data.get("latest_version") or data.get("version") or "—").strip()
    download = str(data.get("download_url") or "").strip()
    notes = str(data.get("release_notes") or data.get("notes") or "").strip()
    notes_html = (
        f'<section class="notes"><h2>更新说明</h2><pre>{html.escape(notes)}</pre></section>'
        if notes
        else ""
    )
    download_html = (
        f'<p class="meta"><strong>安装包</strong> · '
        f'<a href="{html.escape(download, quote=True)}" rel="noopener">{html.escape(download)}</a></p>'
        if download
        else '<p class="meta muted">尚未配置安装包直链</p>'
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>TOA3 manifest · {html.escape(product)} / {html.escape(channel)} · v{html.escape(version)}</title>
  <style>
    :root {{
      --bg: #f1f5f9; --surface: #fff; --text: #0f172a; --muted: #64748b;
      --primary: #2563eb; --border: #e2e8f0; --code: #0f2744;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: var(--bg); color: var(--text); line-height: 1.55;
    }}
    .wrap {{ max-width: 920px; margin: 0 auto; padding: 28px 20px 48px; }}
    header {{ margin-bottom: 18px; }}
    h1 {{ margin: 0 0 6px; font-size: 1.35rem; }}
    .meta {{ margin: 6px 0; color: var(--muted); font-size: 0.92rem; }}
    .meta strong {{ color: var(--text); }}
    .muted {{ color: var(--muted); }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 16px 0 18px; }}
    button, a.btn {{
      display: inline-flex; align-items: center; justify-content: center;
      min-height: 42px; padding: 0 16px; border-radius: 10px;
      font: inherit; font-weight: 600; cursor: pointer; text-decoration: none;
    }}
    button {{
      border: 1px solid var(--border); background: var(--surface); color: var(--text);
    }}
    button.primary {{ background: var(--primary); border-color: var(--primary); color: #fff; }}
    button:focus, a.btn:focus {{ outline: 2px solid var(--primary); outline-offset: 2px; }}
    a.btn {{ border: 1px solid var(--border); background: var(--surface); color: var(--text); }}
    pre.json {{
      margin: 0; padding: 18px 20px; overflow: auto;
      background: var(--code); color: #e2e8f0; border-radius: 14px;
      font: 500 0.88rem/1.55 ui-monospace, "Cascadia Code", Consolas, monospace;
      tab-size: 2; white-space: pre-wrap; word-break: break-word;
    }}
    .notes pre {{
      margin: 0; padding: 14px 16px; background: var(--surface);
      border: 1px solid var(--border); border-radius: 12px; white-space: pre-wrap;
    }}
    .hint {{ margin-top: 14px; font-size: 0.82rem; color: var(--muted); }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>TOA3 更新 manifest</h1>
      <p class="meta"><strong>产品</strong> {html.escape(product)} · <strong>渠道</strong> {html.escape(channel)} · <strong>当前版本</strong> v{html.escape(version.replace("v", "", 1))}</p>
      {download_html}
    </header>
    <div class="actions">
      <button type="button" class="primary" id="btn-copy" autofocus>复制 JSON</button>
      <a class="btn" href="{html.escape(json_url, quote=True)}">原始 JSON</a>
      <a class="btn" href="/admin/app.html">运营台</a>
    </div>
    <pre class="json" id="json-block">{html.escape(pretty)}</pre>
    {notes_html}
    <p class="hint">桌面客户端读取 <code>Accept: application/json</code> 时仍返回紧凑 JSON；浏览器打开默认即为格式化视图。</p>
  </div>
  <script>
    const text = document.getElementById('json-block').textContent;
    document.getElementById('btn-copy').addEventListener('click', async () => {{
      try {{
        await navigator.clipboard.writeText(text);
        const btn = document.getElementById('btn-copy');
        btn.textContent = '已复制';
        setTimeout(() => {{ btn.textContent = '复制 JSON'; }}, 1800);
      }} catch (e) {{
        alert('复制失败，请手动选择上方 JSON');
      }}
    }});
  </script>
</body>
</html>"""
