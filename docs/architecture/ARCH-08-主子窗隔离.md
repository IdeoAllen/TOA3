# ARCH-08 · 主子窗隔离（外壳固若金汤）

> 状态：强制（2026-09-03 主理人裁定）  
> 关联：[`01-平台基础`](ARCH-01-平台基础.md) · [`18-引擎与Harness`](ARCH-05-引擎与Harness.md)

## 1. 一句话

**主窗永不为人质。点菜单必须立刻切壳；Guest 卡死、崩、选不了菜单，都不得锁死或拖垮整窗。**

## 2. 主 / 子

| | 主窗口 Shell | 子面 Guest |
|--|--|--|
| 范围 | 顶栏 · 侧栏 · 状态栏 · ModuleHost 切换 | BasePage / WebEngine / 系统浏览器 |
| 成败 | 导航永远可用 | 可失败、可外置、可回收 |
| 代码 | `app/shell.py` | `modules/*` · `local_web_host` |

## 3. 切页铁律（实现）

1. **先软离 Guest，再切栈** — `soft_leave` / `on_leave` 包在 try 内；拦截 `SystemExit`。  
2. **立刻更新壳 chrome** — 顶栏 / 侧栏当帧响应。  
3. **子页未缓存 → Loading 进度** — `_LoadingGuestPage`（不确定进度条）；下一拍异步 `create_page`；可随时点走取消进页。  
4. **已缓存 → 当帧切真页**，`on_enter` 延后一拍。  
5. **重 Guest 只按需延迟拆 View** — `keep_web_embed_on_leave` 为真则保留；离 web-heavy 进其它页 `on_enter` 延迟 ≥360ms，与 purge 错开。  
6. **进页回调隔离** — `on_enter` 失败只记日志 + 状态栏；拦截 `SystemExit`；WebView 访问前 `isValid`。  
7. **重引擎默认 L2 浏览器表面** — Comfy `prefer_embed: false`。  

完整整改方案见下文「附册 · 原 32」。

## 4. 验收

- 任意菜单首次打开：先见 Loading，壳可立刻切走。  
- 引擎页打开后连点顶栏其它子模块：壳切换流畅，不闪退、不整窗退出。  
- Guest 抛异常 / `sys.exit`：壳仍可回首页。  
- Comfy：浏览器干活，主窗只控制台。

---

## 附册 · 原 32 壳层固若金汤整改方案（已并入，2026-09-07）

> 原独立方案全文如下；自测命令与验收仍有效。

# TOA3 · 壳层固若金汤整改方案（主理人反馈统筹）

> 状态：**收口完成 · Agent 自测通过**（2026-09-03 续：handoff + beforeunload 放行 + painted 断言）  
> 目标一句话：**点任何菜单，主窗必须立刻响应；子页慢可以，崩/退/卡死主窗不可以。**  
> 验收原则：**不依赖主理人手测**。  
> - 铁律：`python scripts/verify_shell_hardening.py`  
> - 引擎↔业务：`python scripts/debug_engines_to_business.py`  
> - 全菜单：`python scripts/stress_all_menus.py`（挂 `verify_all.py`）  
> - 排查法 skill：`.cursor/skills/toa3-sop-debug-crash/SKILL.md`

---

## 0. 使用目标（验收口径）

| # | 用户可感目标 | 验收 |
|---|-------------|------|
| G1 | 顶栏/侧栏任意切换丝滑 | 当帧更新勾选与域；≤1 帧内出现 Loading 或真页 |
| G2 | 子页未就位有 Loading 进度 | 首次打开任意模块先见进度条，可随时点走 |
| G3 | 狂切菜单主程序不退 | 无进程退出；Python 异常不拖垮壳；WebEngine 销毁不原生闪退 |
| G4 | 「系统」一点就进设置 | 不弹回首页、不闪退、不卡 30s |
| G5 | 引擎工作台可点、可稳 | 内嵌清晰可点；少白闪；**ComfyUI 侧栏已隐藏**；**切引擎不串画面** |
| G6 | 媒体工坊不堵壳 | 首次建页异步；点走立刻切其它菜单 |
| G7 | 引擎 → 业务不自退 | `debug_engines_to_business` EXIT=0；faulthandler 无新 AV |
| G8 | Draw 未保存再切引擎 | 不弹离开确认卡死；`painted_url` 为目标引擎端口 |

---

## 1. 反馈映射（已证实）

| 反馈 | 根因 | 对策 |
|------|------|------|
| 媒体工坊点菜单卡 ~2s | 同步建巨页 | Loading + 异步建页 |
| 侧栏多余滚动条 | `ScrollBarAlwaysOn` | `AsNeeded` |
| 多引擎闪退 / 白闪 | 每页各建 Chromium；切页 hide+Stop；重复 setPage/遮罩 | **单例 + handoff（park=False）**；同 URL 不导航；就绪不抬遮罩 |
| Harness 首进抖窗 | 预热 View + 真 View 并存；VBox 双控件 | 预热短命释放；栈式宿主 |
| 点不动（设置主题） | 遮罩穿透层仍盖 WebView | 就绪 **hide** 遮罩 |
| Draw 不能保存 | 未接 `downloadRequested` | `wire_profile_downloads` |
| 引擎网页使用中闪 | 轮询反复 acquire/占位；loadFinished(false) 重载；embed 总抬遮罩 | 热稳态早退；失败不盲重载；`embed_view(loading=…)` |
| **切 Harness 仍见 Draw + 离开确认** | Draw `beforeunload` 挡住共享 View `setUrl`；仍露出旧站 | `begin_forced_navigation` 放行 Confirm；换 URL 前占位；`painted_url` 断言 |
| 引擎→业务「转一下自己退」 | `DataTable` AV（与拆 Web 叠） | 批量 resize + 回填延后；离引擎 shutdown + 1200ms |
| Comfy 难稳 | — | 侧栏 `show: false`（代码保留） |

---

## 2. 架构铁律

```
主窗 Shell = Host（永不做人质）
Guest = BasePage / 共享 WebEngine / 系统浏览器

切页：软离 → 立刻 chrome → Loading 或真页 → 延后 on_enter
引擎：Harness / OpenPencil / Draw.io **共用一份** QWebEngineView
禁止：切页 processEvents；每页各建 Chromium；就绪后穿透遮罩盖 WebView
```

**时序：**

| 场景 | enter_delay | Web 处理 |
|------|-------------|---------|
| 引擎 → 引擎 | **80ms** handoff | 软交接；**不 hide / 不 Stop / 不进 holder** |
| 引擎 → 业务/其它 | **1200ms** | purge + **`shutdown` 销毁共享 View** |
| 非 web → 任意 | 0 | — |

真相源代码：`app/shell.py` · `services/shared_local_webengine.py`

---

## 3. 分波状态

| Wave | 状态 | 要点 |
|------|------|------|
| A 止血 | **DONE** | destroy 清引用；系统域；SystemExit / already-deleted |
| B 丝滑 | **DONE** | Loading；AsNeeded；媒体工坊异步 |
| C 引擎 | **DONE** | 共享 WebEngine；下载；遮罩；Comfy 隐藏；工具条 minH=32 |
| D 品质 | **持续** | `verify_all`；skill `toa3-sop-debug-crash`；禁止进页同步 DMS |

---

## 4. 本轮（续）改动清单

| 文件 | 改动 |
|------|------|
| `services/shared_local_webengine.py` | Harness+OpenPencil+Draw 单例；shutdown destroy 600ms |
| `modules/harness_agent/*` | 改用 shared；栈式宿主；就绪 hide 遮罩 |
| `modules/local_web_host/*` | acquire/release；prefer_embed 默认 true |
| `services/webengine_host.py` | `wire_profile_downloads` |
| `services/webengine_prewarm.py` | 预热后 300ms 释放 |
| `widgets/displays.py` | DataTable 列宽布局防 AV |
| `modules/schedule_reminder/*` | 场景回填延后一拍 |
| `app/shell.py` | 引擎→非引擎 1200ms + shutdown |
| `app/main.py` / `logging_setup` / `app.dev.yml` | DEBUG + faulthandler |
| `.cursor/skills/toa3-sop-debug-crash/` | 闪退 + WebEngine 不清晰/闪烁/点不动排错 |
| `scripts/debug_engines_to_business.py` | 引擎↔业务 DEBUG 复现 |

---

## 5. 明确不做（除非新开评审）

- ComfyUI（大成哥-2）侧栏菜单整项（代码保留）  
- Portal 远程下发菜单  
- 切页 `processEvents`「催」WebEngine  
- 用 `prefer_embed: false` **掩盖**多 Chromium（OpenPencil/Draw **默认内嵌**；Comfy 仍浏览器且菜单隐藏）

---

## 6. 验收勾选（Agent）

| 脚本 | 覆盖 | 期望 |
|------|------|------|
| `verify_shell_hardening.py` | Loading / 系统域 / Comfy 隐藏 / enter_delay / handoff / beforeunload | OK |
| `debug_engines_to_business.py` | Harness↔Draw↔日程 + **painted 断言** + beforeunload 陷阱 | SESSION OK · EXIT=0 |
| `stress_engines_business.py` | 引擎往返 × 业务 | OK |
| `stress_all_menus.py` | 全可见菜单 | OK（建议关正式版 TOA3 再跑） |

挂入：`scripts/verify_all.py`。

原生崩查：`common/logs/toa3_faulthandler.log`。

---

## 7. 主理人目标 ↔ Wave

| # | 目标 | Wave |
|---|------|------|
| 1 | 主框架稳定 | A · G3 |
| 2 | 内页 Loading | B · G2 |
| 3–4 | 线性状态 / 文案稳 | C |
| 5–6 | 不闪、Host 条矮 | C |
| 7–8 | 引擎真进来、控件清晰可点 | C · G5 |
| 9 | 停服平稳 | C |
| + | 引擎切业务不自退 | G7 · DataTable + shutdown |