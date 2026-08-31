# 28d · 用户扩展 WebView 表面

> 状态：**approved** · 2026-08-30  
> 关联：`28-Harness驱动的业务插件开发范式` · `28c-扩展开发安全快稳策略` · `18-Harness嵌入与壳层结合`

## 1. 定位

| 表面 | 适用 | 产物 |
|------|------|------|
| `entry.surface = qt`（默认） | 表单、台账、生成类 | `modules/<id>/<id>_page.py` + widgets |
| `entry.surface = webview` | 游戏、可视化、复杂交互 | `ui/index.html` + JS/CSS |

Harness 写 HTML/JS 比 Qt 布局快；宿主提供 **统一 WebEngine 壳 + QWebChannel 白名单桥**，扩展不得自行 `import QWebEngineView`。

## 2. 契约（plugin.toml）

```toml
[entry]
surface = "webview"
web_root = "ui/index.html"
class_name = "WebExtensionHost"   # 占位，运行时由宿主页加载
page_id = "<plugin_id>"
```

- 资源仅放扩展根内，默认 `ui/`
- 导航限制：`file://` 仅限扩展根；`http(s)` 须 `[safety] allow_network = true`
- 与 Harness Guest（dsh web）无关，不共用 URL

## 3. 宿主桥（JS · 对象名 `toa`）

见扩展内 `HOST_API.md`。页面须引入：

```html
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="toa_bridge.js"></script>
```

```javascript
TOA.ready(function (toa) {
  toa.reportStatus('就绪', 'success');
});
```

## 4. 代码落点

| 层 | 路径 |
|----|------|
| 宿主页 | `core/extension_web_page.py` |
| QWebChannel 桥 | `services/extension_web_bridge.py` |
| JS 助手（脚手架复制） | `assets/extension_web/toa_bridge.js` |
| 加载分支 | `services/plugin_loader.create_plugin_page` |
| 脚手架 | `services/plugin_scaffold.py`（`surface=webview`） |

## 5. 验收

1. 创建扩展时选「网页界面」→ 目录含 `ui/index.html`
2. 开发完成 → 业务侧栏打开 → WebEngine 显示本地页
3. `toa.reportStatus` 出现在状态栏
4. 未声明 `allow_network` 时外链导航被拦截
5. `python scripts/audit_plugin.py <root>` 通过

样例：`assets/samples/toa_plugin_pack/demo_web/`
