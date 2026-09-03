# 本地 Web 引擎嵌入范式（Host + Guest）

> 状态：规范草案（主理人认可后升为强制）  
> 适用：Harness、OpenPencil、ComfyUI Web、Draw.io，以及 **引擎宿主扩展包**  
> 对照：[`18-Harness嵌入与壳层结合.md`](./18-Harness嵌入与壳层结合.md)

## 1. 一句话

**Guest = 开源项目原版 Web UI（同一 localhost URL）；Host = TOA 只做安装 / 启停 / 健康 / 内嵌。**  
用户不必再维护多个终端窗口——装、开、停、看都在一个软件里。  
禁止山寨第二套业务界面。

## 2. 扩展三分面（产品口径）

| 类型 | 落点 | Host 做什么 | Guest |
|------|------|-------------|-------|
| **业务插件** `surface=qt` / `webview` | `data/user/extensions` | 控件库页或 HTML | 用户自写业务 |
| **引擎宿主包** `engine pack` | `data/user/engine_packs/<id>/engine.yml` | 安装探测·启停·内嵌 | 第三方原版 Web |
| **官方引擎模块** | `config/local_web_engines.yml` + 薄 `*Page` | 同上（发版内置） | 同上 |

引擎宿主包与业务插件隔离：前者挂顶栏 **引擎**，后者挂 **业务**；都不改 Guest 源码。

## 3. 生命周期铁律（健壮 · 丝滑）

```
未安装 → 一键安装（进度条）或「指定目录」
已安装 → 探测端口
未启动 → 自动启动（可关）并写日志
已启动 → prefer_embed=true 内嵌；prefer_embed=false 系统浏览器（外壳隔离）
离开页 → 默认可不停服务；「停止」显式回收
```

### 3.1 表面策略（外壳固若金汤）

| 引擎 | 默认 `prefer_embed` | 原因 |
|------|---------------------|------|
| OpenPencil / Draw.io | `true` | 轻量，内嵌可接受 |
| **ComfyUI** | **`false`（浏览器）** | Chromium 节点编辑器会抢焦点/拖垮主窗；模型下拉须完整浏览器 |

页内可「改用内嵌 / 改用浏览器」，写入 `data/user/local_web_engines.yml`。  
壳层仅在 `uses_webengine_embed()` 为真时走 WebEngine 延迟销毁路径。

验收：

1. 拔掉根目录 → 进页出现安装门，不一白屏。  
2. 已装未启 → 进页自动启动，状态条可见「正在启动…」。  
3. Comfy 已启 → **系统浏览器打开同一 URL**，主窗只留启停控制台；顶栏/侧栏仍跟手。  
4. 其它 `prefer_embed=true` 引擎 → 进页内嵌；失败可用「浏览器打开」。  
5. 启动进程秒退 → 提示读 `data/.../local_web_engine/logs/<id>.log`。

## 4. Host 能力白名单

| 能力 | 为何在 Host |
|------|-------------|
| 一键安装（git + post）/ 指定目录 | 免终端 clone |
| 启停 / 自动启动 | 免多个 cmd 窗口 |
| 健康条 + 内嵌 | 未就绪不盲等 |
| 浏览器打开同一 URL | 排障备用 |

**禁止**：自研替代 Guest UI、改 Guest CSS、默认注入业务 JS。

## 5. 代码落点

| 层 | 路径 |
|----|------|
| 官方目录 | `config/local_web_engines.yml` |
| 扩展包 | `data/user/engine_packs/<id>/engine.yml` · 样例 `assets/samples/engine_packs/` |
| 运行时 | `services/local_web_engine/`（含 `install.py` · `packs.py`） |
| 页基类 | `modules/local_web_host/local_web_host_page.py` |
| 扩展包页 | `modules/local_web_host/engine_pack_page.py` |
| 校验 | `python scripts/verify_local_web_engines.py --start-all-light` |

新增官方引擎：yaml + 薄 Page + `app.yml` + manifest。  
新增用户引擎包：复制样例目录 → 改 `engine.yml` → `menu_show: true` → 重启。

## 6. 内置四引擎

| id | Guest | 安装 | 端口 |
|----|-------|------|------|
| `harness_agent` | DeepSeek Harness | 一键 npm / 指定 | `web_port`（如 3082） |
| `open_pencil` | OpenPencil | git + bun/npm | 1420 |
| `drawio_web` | draw.io webapp | git clone | 8080 |
| `comfyui_web` | ComfyUI | 指定大成哥-2（体积大，无一键全量） | 8189 |

## 7. 独到之处（草案）

1. **一套 Host 多 Guest** — yaml / 引擎包即可扩展。  
2. **安装→启动→加载一条链** — 进页自动收敛，不丢终端。  
3. **扩展包与业务插件分轨** — 引擎进「引擎」，业务进「业务」，可移除互不影响。
