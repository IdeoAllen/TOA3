---
name: toa3-sop-debug-crash
description: >-
  TOA3 闪退/抖窗/WebEngine 内嵌页不清晰·闪烁·点不动排查：开 DEBUG、跑复现脚本、
  读会话日志与 faulthandler，按症状表定点修。Use when 闪退、自己退了、ACCESS_VIOLATION、
  0xC0000005、抖窗、点不动、不清晰、发虚、闪烁、白闪、引擎切业务崩、WebEngine、
  Harness、Draw.io、OpenPencil、看日志、debug、排查.
---

# TOA3 · 闪退 / WebEngine 内嵌排查

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

主理人说「闪退 / 自己退了 / 抖窗 / 点不动 / 不清晰 / 闪烁」时：**禁止猜**，开 DEBUG 自跑复现，用日志或症状表钉死再改。

## 铁律

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

1. **Agent 自测**，不让主理人当测试员。  
2. **无 Python 异常 ≠ 没事** — 原生闪退常是 `0xC0000005` / exit `-1073741819`，只在 `toa3_faulthandler.log`。  
3. **先复现再改**；改完必须再跑同一脚本到 `OK`。  
4. 本机若有 **正式版 TOA3.exe** 与开发版并存，会抢 WebEngine 缓存；诊断时优先关掉正式版。  
5. 引擎内嵌：**一套 Host + 共用一份 WebEngine**（`shared_local_webengine`），禁止每页各建 Chromium。

## 何时使用

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

- 切顶栏（尤其 **引擎 → 业务**）转一下自己退  
- Harness / Draw.io / OpenPencil：**不清晰、闪烁、点不动、不能保存**  
- 日志在某句「正在…」后突然断、无 Traceback  
- 用户说：开 debug、看日志、排查闪退 / WebEngine  

---

## A. WebEngine 内嵌页 · 三种症状排错

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

内嵌 Guest（Harness / Draw / OpenPencil / 网页工作台）出问题，**先对症状再查表**，不要一上来改业务逻辑。

### A0. 共通检查（三种都先做）

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

| # | 检查 | 通过标准 |

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。
|---|------|----------|
| 1 | 是否双开正式版 | 日志无「正式版运行中：开发版已停用…」；任务管理器只留开发进程 |
| 2 | 是否多份 View | 日志里同一时段不该反复「已创建共享…」+ 另有独立 Profile 建 View |
| 3 | 预热是否占坑 | 真 View `acquire` 前须 `release_prewarm_hold`；预热 View 不得长期存活 |
| 4 | 是否走统一入口 | `apply_webengine_view_defaults` +（引擎）`shared_local_webengine.acquire` |

---

### 症状 1 · 不清晰 / 发虚 / 发糊

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

**用户感知：** 字糊、线锯齿、125%/150% 屏发虚。

| 排错 | 查什么 | 改哪里 |
|------|--------|--------|
| **1a HiDPI** | 是否用逻辑像素硬画、忽略 DPR | 位图/图标走 `icon_registry`；Web 侧看 `setZoomFactor` 是否过小；禁止整页 `devicePixelRatio` 乱设 |
| **1b 字体旗标** | Chromium 字体抗锯齿 | `app/main.py` `_configure_webengine_env`：保留 `--enable-font-antialiasing`、`--font-render-hinting=full`；**勿**长期 `--disable-gpu`（会糊且卡） |
| **1c 缩放** | 模块自己的 web_zoom | Harness `web_zoom` 等；默认约 1.0；异常小/大都会糊或虚 |
| **1d 主题/QSS** | 外层控件模糊 ≠ Web 内糊 | 分清是壳按钮糊（图标门禁）还是 Chromium 内糊 |

**自测：** 125% / 150% 各看一眼引擎页正文与侧栏图标。

---

### 症状 2 · 闪烁 / 白闪 / 首进抖窗

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

**用户感知：** 进页整窗抖一下、白闪、遮罩闪、悬停闪。

| 排错 | 查什么 | 改哪里 |
|------|--------|--------|
| **2a 双 Chromium** | 预热 View + 真 View 并存；或每引擎各建 View | `webengine_prewarm` 短命释放；引擎只用 `shared_local_webengine` |
| **2b 布局抖** | VBox 里 placeholder 与 View 同时 stretch；频繁 show/hide | 宿主用 **QStackedLayout**（占位/View 互斥）；参考 Harness / LocalWebHost |
| **2c 遮罩闪** | 不透明 overlay 反复 show/hide；就绪仍 `embed_view` 抬罩 | 加载期可挡；**就绪必须 hide**；`embed_view(loading=False)` |
| **2d 焦点抢夺** | 进页 `setFocus` 给 WebEngine | `primary_focus_widget` 勿默认 WebView；禁止 MousePress→setFocus 过滤器 |
| **2e GPU/合成** | 日志 `context is marked as lost` / GLES 失败 | `AA_ShareOpenGLContexts`；`--use-angle=d3d11`；`--disable-features=CalculateNativeWinOcclusion`；切页后 `shutdown` 再进业务 |
| **2f 切页叠崩** | 离引擎立刻建业务重页 | `enter_delay` 加长；共享 View `shutdown(destroy=True)` |
| **2g 引擎互切白闪** | 先 purge hide+Stop 再 acquire；反复 `setPage` | 壳层 `_handoff_engine_embed`（80ms）；`release(park=False)`；同 URL 不导航；只改 `set_accept_nav` |
| **2h 使用中闪** | 轮询反复占位/acquire；`loadFinished(false)` 盲重载 | LocalWebHost 热稳态早退；已显示则忽略失败回调 |
| **2i 切引擎串画面** | Draw「离开页面」Confirm 挡住 `setUrl`；Host 条已是 Harness | `begin_forced_navigation`；换 URL 前占位；`painted_url` 断言 |

**自测：** `python scripts/debug_engines_to_business.py`；首进 Harness 目视无整窗抖。

---

### 症状 3 · 点不动 / 点哪都卡 / 切换不了

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

**用户感知：** 设置里主题点不上、侧栏切不走、像冻住。

| 排错 | 查什么 | 改哪里 |
|------|--------|--------|
| **3a 遮罩挡点击** | Overlay 仍 `show`，即使 `WA_TransparentForMouseEvents` | **就绪后必须 hide**。穿透层盖在 `QWebEngineView` 上仍会吞 Chromium 命中（已踩坑） |
| **3b 误装焦点过滤器** | MousePress 里 `setFocus` | `apply_webengine_view_defaults` 清理 `_toa_focus_filter`；勿再装 |
| **3c 整窗冻更新** | `setUpdatesEnabled(False)` | **禁止**为消闪冻主窗（顶栏会像一点就退） |
| **3d disable-gpu** | 环境变量残留 | `_configure_webengine_env` **剥离** `--disable-gpu*`（压测脚本除外） |
| **3e 保存/下载无反应** | Draw「Unsaved…」点了没对话框 | `wire_profile_downloads`；`chooseFiles` / FileSelectSave |
| **3f 壳层未切走** | soft_leave 未 purge，焦点仍在 Web | shell `_clear_webengine_focus` + purge；日志看 `purge web embed` |

**自测：** 进 Harness 开设置点「深色」；Draw 点保存应出「另存为」。

---

### 症状分流（一句话）

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

```text
不清晰 → 先查 DPR / 字体旗标 / zoom / 误关 GPU
闪烁   → 先查双 View、预热、栈布局、遮罩、焦点
点不动 → 先查遮罩未 hide、焦点过滤器、冻窗、disable-gpu、下载未接
闪退   → 走下方 B 节 faulthandler（可能是表头与拆 Web 叠崩，不是「菜单自己退」）
```

---

## B. 闪退 / 自退（强制顺序）

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

### 1. 打开 DEBUG

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

| 项 | 做法 |
|----|------|
| 开发配置 | `config/app.dev.yml` → `log_config.log_level: DEBUG` |
| 原生栈 | `faulthandler` → `common/logs/toa3_faulthandler.log` |

### 2. 选复现脚本

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

| 症状 | 脚本 |
|------|------|
| 引擎 ↔ 业务闪退 | `python scripts/debug_engines_to_business.py` |
| 引擎切换压测 | `python scripts/stress_engines_business.py` |
| 全菜单压测 | `python scripts/stress_all_menus.py` |
| 壳层铁律 | `python scripts/verify_shell_hardening.py` |

```powershell
cd TOA3
python scripts/debug_engines_to_business.py
echo EXIT=$LASTEXITCODE
```

### 3. 读三份日志

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

1. **`toa3_faulthandler.log`** — `access violation` 栈顶 = 真凶  
2. **`toa3_debug_session.log`** — `STEP navigate→` 死在哪步  
3. **`toa3.log`** — `navigate` / `acquire` / `release` / `purge`  

| 现象 | 含义 |
|------|------|
| 停在「正在查询课表」+ fault→`DataTable` | 表回填与拆 Web 叠崩 |
| fault 在 WebEngine / 无 Python 帧 | Chromium/GPU；双实例、多 View |
| 「正式版运行中…」 | 先关正式版再测 |

### 4. 定点修（闪退）

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

| 指向 | 动作 |
|------|------|
| `displays.py` `_apply_column_layout` | 加固 DataTable；回填延后一拍 |
| 多 View / shared | 单例 + 离引擎 `shutdown` + `enter_delay` |
| 预热 | 短命 `release_prewarm_hold` |

### 5. 回归

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

```powershell
python scripts/debug_engines_to_business.py   # SESSION OK, EXIT=0

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。
python scripts/verify_shell_hardening.py
```

---

## 关键路径

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

| 文件 | 用途 |
|------|------|
| `services/shared_local_webengine.py` | 引擎单例 View |
| `services/webengine_host.py` | 默认设置、下载、选文件 |
| `services/webengine_prewarm.py` | 预热（须短命） |
| `app/main.py` | Chromium 旗标、faulthandler、ShareOpenGL |
| `app/shell.py` | navigate / purge / enter_delay |
| `modules/harness_agent/harness_agent_page.py` | 遮罩/栈宿主范例 |
| `modules/local_web_host/local_web_host_page.py` | Draw/OpenPencil Host |
| `scripts/debug_engines_to_business.py` | DEBUG 复现 |

## 禁止

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

- 无日志/无症状表就改「感觉像菜单」  
- 用 `prefer_embed: false` 掩盖多 WebEngine（产品要内嵌时）  
- 就绪后仍 show「穿透」遮罩盖 WebView  
- 为消闪 `setUpdatesEnabled(False)` 冻主窗  
- 让主理人「再点一遍」代替脚本  

## 汇报模板

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

```text
症状：不清晰 / 闪烁 / 点不动 / 闪退
排错：A1a… / A2b… / A3a… 或 faulthandler → file:line
修复：<文件>
回归：SESSION OK / 目视 125%·150% / 点击·保存可用
```
