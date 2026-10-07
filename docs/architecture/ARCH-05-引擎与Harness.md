# ARCH-05 · 引擎与 Harness（原 18 + 29 合订）

> 本文为整合稿（2026-09-07）。原分册已进 `docs/_archive/architecture/`。  
> 总入口：[`../README.md`](../README.md)  
> **全生命周期 / 双版本 / 打包 / 升级整改 / G0 自用自排错**：见 [ARCH-10](ARCH-10-Harness全生命周期.md)（待专家组论证）。

---

## 原分册：18-Harness嵌入与壳层结合.md

# Harness 嵌入与壳层结合

> 编码智能体 · `harness_agent` · 与 `docs/research/harness_agent-top3.md` 配套

## 1. 一句话

**Guest = 正版 DeepSeek Harness Web（同一 URL）；Host = TOA 原生壳（启停、办公链、只读侧栏）。**  
用户感到「一个整体」，是因为外框、工具栏、侧栏都是 TOA 控件库；中间干活区仍是 Harness 官方界面，不是山寨聊天页。

## 2. 双表面（同一 Sidecar）

| 表面 | 实现 | 数据 |
|------|------|------|
| **内嵌** | `QWebEngineView` → `http://127.0.0.1:{web_port}` | 与浏览器共用 `DSH_HOME`、同一 dsh 进程 |
| **系统浏览器** | `webbrowser.open(web_url())` | 会话/工作区仍在 Harness 内，不另开「TOA 版」 |

切换规则（与 `config/harness.yml` 一致）：

- **现行默认 `surface_mode: embed`（2026-09-11b）**：启动后**套件内嵌**官方 Web；外开须用户自点「在浏览器打开」，**禁止自动弹浏览器**。  
- **侧栏文件预览（2026-09-22）**：启动前须 `QWebEngineUrlScheme.registerScheme("dsh-resource")`（`Syntax.Host`），否则 JS `new URL('dsh-resource://file/…')` 的 hostname 为空 → 「文件资源服务不可用」。实现：`services/qt_webengine_bootstrap.register_dsh_resource_url_scheme`；门禁 `scripts/verify_dsh_resource_url_scheme.py`。  
- **能力不及处明示**：其余 Qt WebEngine ≠ 完整 Chrome 的能力，仍提示「浏览器打开效果更佳」。  
- **启停体验内外一致**：安装 / 启动 / 停止 不因表面分叉；浏览器只是同一 Sidecar 的可选完整 Guest 面。  
- **禁止**默认自动外开逼用户跳窗；**禁止**第二套 Web 地址或 TOA 自研 Agent 页替代 `dsh web`。  
- `engine_host_hub`：**Hold**（菜单隐藏）；勿再做成默认入口。

### 2.1 Host 进度与装载契约（全引擎通用 · 2026-09-10）

适用于：`harness_agent`、`LocalWebHostPage`（OpenPencil / Draw.io / ComfyUI / engine pack）、Hub 适配页。  
标准条目：`STD-01` **A4.7**。

| 阶段 | 用户看到什么 | 禁止 |
|------|-------------|------|
| 进页检测 / 查安装 / 查服务 | 状态行轻提示即可；主区结果态（未启动/已停止/装载中） | `ProgressBar.show/hide` 顶布局；进页就弹活动条；「正在进入」盖住「已停止」 |
| 启动 / 停止 / 重启 | `SoftActivityBar` 虚线跑马灯淡入滚动；点按可 `immediate` | 系统 indeterminate 咔咔跳；装完还在往后跑 |
| 失败 / 异常 | Host 自读日志出短因；引导「修一下」/「环境维护」；修完自动重启 | 堆栈刷屏；叫用户打开日志；修复常驻成第二主 CTA；系统设置堆路径表单 |
| 进页已在跑 | HTTP 通则直接装载界面，禁止因修密钥整段重启 | 已运行还整页重启 |
| 界面装载 | 主区**占位遮罩**（栈内 placeholder）；Web 藏在后面 | 半露 Web、半透明盖 Chromium、状态文案闪烁抢主区 |
| 装载完成 | `loadFinished` 成功 → 硬停活动条 → 揭开 Web | READY 后活动条继续扫 |
| 深链 / 卡死回主 | 「刷新」与「更多→回到主界面」强制 `setUrl(web_url())`；装载超时看门狗揭罩或回主 | 只 `reload()` 当前深链导致永久遮罩 |
| 一键安装 | 确定进度 `ProgressBar` 0–100（仅安装门；分阶段文案：连接/下载/校验/解压/配置） | 用安装条冒充启停/进页检测；干等无进度 |

**控件**：活动条必须用 `widgets.SoftActivityBar`（`objectName=SoftActivityBar`，QSS 已登记）；禁止业务 `setStyleSheet`。  
**实现参考**：`modules/harness_agent/harness_agent_page.py` · `modules/local_web_host/local_web_host_page.py`。  
**验收脚本**：`scripts/verify_harness_host_lifecycle.py` · `scripts/verify_local_web_host_chrome.py`。

## 3. 布局（Host + Guest · v2）

```
┌─ 状态 + 主操作（启停/投喂/表面切换） ─────────────┐
├─ [仅首次] 单行引导 → 系统设置 ─────────────────────┤
├─ [有办公链时] 投喂条 ──────────────────────────────┤
├──────────────────────────────────────────────────┤
│           Harness 原版 Web（Guest · 全宽）          │
└──────────────────────────────────────────────────┘
```

- **不建**左会话索引、右用量仪表 — 与 Harness 内左侧栏/设置 **100% 重复**，已移除。
- 会话切换、工作区、插件、用量详单：**只在 Harness Web 内操作**。

## 4. TOA Host 能力清单（每项须能回答「为何不在 Harness 里做」）

| 能力 | TOA 独有价值 | 入口 |
|------|-------------|------|
| 双路线一键安装 | 官方精简 / 预制必备 zip；免 Node/npm/终端 | SetupGate 选版本 |
| Sidecar 启停/重启 | 用户不开终端；与套件托盘/热键一体 | 主按钮 / 更多 |
| 启动前 denylist 自愈 | 拦截不兼容插件拖死 Web（Failed to load plugins） | 自动（prepare / restart） |
| 修复 / 配置快照回退 | 坏了点修；健康时标「上次可用」可一键回 | 更多 |
| 启动日志 / 安装目录 | 出问题看得见，不必翻终端 | 更多 |
| 一键卸载（默认可留会话） | 干净走人，不必手删 `~/.toa3` | 更多 |
| 内嵌 ↔ 浏览器 | 同一 DSH_HOME，随场景切换表面 | 工具栏 |
| 办公链投喂 | 剪贴板/OCR → Harness 输入（套件闭环） | 投喂条 / 投喂 |
| 导出最近会话 MD | 落盘 `output/`，培训留档可追溯 | 更多 |
| 首次环境引导 | 小白四步：选版本 → 可预期等待 → 一次 Key → 检测启动 | SetupGate |
| 路径/密钥/端口 | 页内「环境维护」；系统设置不填路径 | 系统设置堆 DSH/Node/bin |

### 4.1 四步开用（C′ 无感就绪 · 装门）

1. **选择安装版本**：官方精简（仅核心 Web、无扩展插件）或预制必备（核心 + `prefab_essential_plugins` 白名单）。  
2. **可预期等待**：下载 → 校验 sha256 → 解压 → 配置；确定进度条；可取消。  
3. **配置一次 API Key**：仅写本机 `.credentials.yaml`。  
4. **检测状态 → 启动服务 → 即可应用**（内嵌 Guest）。

预制包 URL / sha256 见 `config/harness.yml`（`official_bundle_*` / `prefab_bundle_*`）；构建脚本 `scripts/build_harness_prefab.py`。主安装器**不**内嵌 zip（体积大，发版 guard 禁止打进 Setup）。URL 未配置且本机有 Node 时可回落 npm；日常主路径不出现 npm 文案。

### 4.2 小白原则（主理人 · 2026-09-11）

用户一般不懂技术；**复杂配置 = 摆设**。产品口径：

- **日常唯一路径**：编码智能体页内四步；只要求「选一次版本 + 贴一次 Key」。  
- **日常入口**：顶栏「引擎 → 编码智能体」四步开用 +「更多 → 环境维护」（对话密钥、怎么看界面、修一下 / 回到上次能用的样子 / 更新环境）。  
- **系统设置 · 能力接入**：不再设 Harness 页签；OCR / 连通总览仍在此。  
- **禁止**把「设置页再配一遍」当成正常开箱步骤；Key 与引擎页是同一套本机数据。

## 5. TOA 原生面 **禁止做**（山寨红线）

- 自研聊天/Agent 输入框作为主界面
- TOA 内 **dsh/Cordis** 插件安装器（须在 Harness / `dsh plugin` 或 Harness 设置）
- TOA 内工作区管理器（须在 Harness 左侧工作区）
- 把 Harness 插件误当成 TOA 侧栏模块（TOA **业务插件包**另见 `ARCH-07-用户扩展范式.md`）
- 注入 CSS 改 Harness 主题（默认 `theme_harmonize: false`）
- 默认自动 JS 填输入框（默认 `feed_auto_inject: false`；以剪贴板为主）

## 6. 合格验收（结合得好）

1. 内嵌与浏览器打开 **同一 URL**，会话在 `DSH_HOME` 下连续。
2. 未启动时单行引导可完成配置；启动后 Harness Web 全宽。
3. 无 TOA 侧会话/用量重复 UI；会话与工作区仅在 Harness 内。
4. 剪贴板/OCR「送到智能体」→ 复制 + 进页，在 Harness 输入框粘贴（与浏览器版一致）。
5. `python scripts/audit_migration.py` 通过；无新增「替代 Harness 主路径」的菜单项。

## 7. 代码落点

| 层 | 路径 |
|----|------|
| 页面 Host | `modules/harness_agent/harness_agent_page.py` |
| Web 容器 | `modules/harness_agent/web_host.py` |
| 首次引导 | `modules/harness_agent/setup_gate.py` |
| 办公链条 | `modules/harness_agent/feed_strip.py` |
| 状态探测 | `services/harness_probe.py` |
| 导出 | `services/harness_export.py` |
| 一键安装 | `services/harness_setup.install_harness_runtime` · `services/harness_prefab` |
| 预制构建 | `scripts/build_harness_prefab.py` |
| 双表面 | `services/harness_surface.py` |
| Sidecar | `services/harness_sidecar.py` |
| 配置 | `config/harness.yml` · `data/user/harness.yml` |
| UI 偏好 | `services/harness_ui_prefs.py` · `data/module/harness_agent/ui_prefs.json` |

## 8. 产品重构 v2（2026-08-27）

**结论**：左/右只读侧栏与 Harness 内 UI 重复，制造「眼花缭乱」且无独到处 → **整页移除**。

**§3.5 独到之处 #1 修订**：由「三栏指挥台」改为 **「套件内全宽 Harness + 零终端启停」** — 一体感来自同一安装包与办公链，而非复制 Harness 会话/用量 UI。

| 验收 | 标准 |
|------|------|
| 首屏 | 仅状态条 + Harness Web，无第三套会话列表 |
| 投喂 | 办公链进页出现可操作条，一键送入 Harness |
| 导出 | 更多 → 导出最近会话 → `show_saved` + output 目录 |
| 配置 | 未完成四步时页内引导；系统设置仅排障，不作为日常功课 |

---

## 原分册：29-本地Web引擎嵌入范式.md

# 本地 Web 引擎嵌入范式（Host + Guest）

> 状态：**现行强制**（与 `config/local_web_engines.yml` 对齐）  
> 适用：Harness、OpenPencil、ComfyUI Web、Draw.io，以及 **引擎宿主扩展包**  
> 对照：本文前半「原分册：18-Harness」

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

