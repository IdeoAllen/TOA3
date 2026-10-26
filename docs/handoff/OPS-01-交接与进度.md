# OPS-01 · Agent 交接与进度

> **编号**：OPS-01 · 进度唯一文件  
> **规范入口**：`docs/规范/00-规范清单.md` · Skill：`toa3-dev-suite`  
> 更新：2026-09-08

---

## 0. 开场

| 问 | 答 |
|----|----|
| 产品 | 运营宝 / TOA3，PySide6 桌面办公套件 |
| 只改哪 | 只改本仓库 TOA3；TOA2 封板 |
| 写码门禁 | **无开工障碍门禁**（2026-09-14）：有需求直接并行写码；研究/专家组可选。对外可商用仍过 **A10.4** |
| 完成 | `migration_manifest` gaps 空且主理人认可才 `done` |
| 进度 | **只改本文（OPS-01）** |
| 排期 | `docs/PROD-01-功能清单与优先级.md` |
| 产品话术 | `docs/PROD-02-商务产品手册.md`；运行时 `config/product.yml` |
| 工程标准 | `docs/规范/STD-01-工程标准与流程.md` |

**Skill 全套**：`toa3-dev-suite`（入口）· `toa3-sop-new-feature` · `toa3-sop-theme-control` · `toa3-sop-module-accept` · `toa3-sop-quality-pipeline` · `toa3-sop-packaging` · `toa3-sop-commercial-release`（SOP-08 商业发行验收）· `toa3-sop-debug-crash` · `toa3-sop-user-extension` · `toa3-sop-docs-handoff`

```powershell
python scripts/verify_all.py
python -m app.main
```

---

## 1. 一句话现状

**发版待点按钮 v3.1.24（2026-10-12）**：直链 200 · https://www.yczh.tech/downloads/TOA3-Setup-v3.1.24.exe ；运营台已预登记（`is_current=false`，id=19）。git `cdf8c71`。**主理人只点「设为当前」** → Agent 再 `--from-live --require-match --commit`。  
**商业发行整改（同日）**：CDN TLS 已恢复；`verify_license_gate` 进门禁；生产禁 DMS fallback；侧栏收口凑数 mvp/Wave F；SOP-08 Skill。近程产品闸仍是 **主理人点验 Wave★**（勿假清 gaps）。商用冒烟人工 1–5 仍须勾。  
**Harness 启动（2026-09-28）**：用户 `harness.yml` 的 `dsh_bin` 指到 `dsh-guard.mjs` 后，3.1.23 按五级父目录把启动器写到 `C:\Users\toa_dsh_launch.mjs` → Errno 13。已改回正式 `bin.js`；源码改为包装脚本直接执行、启动器只落 `~/.toa3/harness-runtime`。主理人需完全退出运营宝再开。  
**发版 v3.1.23**：直链 200 · https://www.yczh.tech/downloads/TOA3-Setup-v3.1.23.exe ；toa-service stable manifest 已回报 **3.1.23**（2026-10-12 探测）。若列表尚未「设为当前」→ 主理人点一次；已切版 → Agent `--from-live --require-match --commit`。  
**v3.1.24** 上一版：https://www.yczh.tech/downloads/TOA3-Setup-v3.1.22.exe 。  
**发版提交口径**：上传脚本自动 commit 多数跳过；**设当前版后 Agent 必须再跑** `--from-live --require-match --commit` 并回报 hash。  
**全局介入档案**：`ARCH-11` + `global_shell_features` + `verify_global_shell`；Mac 仅口径。  
**v3.1.17** 热键/预览；**v3.1.16** Harness CDN；**v3.1.14** 图片预览。
**双产品商业**（已回写）：DMS=专业高门槛可售；TOA=免费钩子+高级付费；腾讯文档轻量轨；并行不强绑。  
**培训交付看板** `training_delivery_board`：**mvp 已落地**（业务侧栏 order=5，需授权）；班级 handoff + 串链六环；亮点研究 `approved`。待主理人点验清 gaps。  
**助教招聘稿** `assistant_recruit_post`：**mvp 已落地**（业务侧栏 order=45）；命名即表单 + 话术锁定 + 复制即发；research `approved`。待点验清 gaps。  
**助教打卡换装** `assistant_outfit_swap`：**mvp 已落地**（业务侧栏 order=46）；目录全量 + 着装预设 + 只换服装保水印；经 image_gen 编辑；research `approved`。待点验清 gaps。  
**Harness（2026-09-10）**：`@nanmicoder/dsh-agent-teams` 依赖缺失 `uiConversation` → Failed to load plugins；已剔除并重启 `3082`；新增 profile **配置快照/恢复上次可用**（编码智能体 → 更多）；sanitize denylist。  
**Harness 启动失败 mkdir 联接（2026-09-20）**：正式版 sidecar 日志 `UNKNOWN mkdir …/profiles/web/node_modules`——整树 JUNCTION 与新版 dsh `mkdirSync` 冲突。已把本机改成真目录+子联接并成功启动 3082；代码改为启动前自愈、禁止再做整树联接（下一版安装包带上）。
**Harness 会话管理/技能总览红点（同日）**：sanitize 把本机 `link:` 的 `@dachengge/dsh-session-manager` / `dsh-skill-catalog` 当「无法解析」洗掉；已改保留有效 link/file 依赖，并从 last_good 恢复后重启 3082。
**Harness 稳定 Host（同日续）**：按 ARCH-09 六件套收口——启动前 `preflight` 强制剔杀手插件；健康就绪节流标「上次可用」；失败自动再剔并重启；更多菜单补 **打开启动日志 / 安装目录 / 卸载（默认保留会话）**。  
**Harness 交互压测（同日）**：抽出 `harness_chrome` 状态机（启/停/进度/忙碌互斥）；修修复→重启被 `finally` 清 busy、链式重启二次确认；`scripts/verify_harness_host_lifecycle.py --live` 启停往返已绿。  
**Harness 启停口径统一（同日）**：内嵌/浏览器共用同一套进度与结果态；「启动服务」为主 CTA；「在浏览器打开」为次要另开窗；进页清掉离页残留占位；主区有 WebEngine 时始终装载（偏好仅控制是否另开浏览器）。  
**引擎 Host 进度契约（同日）**：写入 `STD-01` A4.7 + `ARCH-05` §2.1；`SoftActivityBar` 仅启停；装载遮罩至 loadFinished；`LocalWebHostPage`（OpenPencil/Draw.io/Comfy）与 Hub 适配已对齐；`verify_local_web_host_chrome.py`。  
**Harness 深链回主（同日）**：内嵌跳到 dsh 新页面后刷新只 reload 深链 → 永久「正在装载」；现改为「刷新 / 更多→回到主界面」强制 `setUrl(web_url())`，装载 8s 看门狗揭罩或回主，失败态同域仍揭开。  
**Harness 402（同日）**：Host/插件正常；截图「Insufficient Balance / QUOTA」= DeepSeek 账户余额不可用（探测 CNY 透支）；本机 env 脏 Key 已用 `ensure_owned_with_credentials` 接管注入设置页 Key。充值后即可继续，重启 alone 消不了 402。  
**Harness API Key 无效（同日晚）**：Windows 用户级 `DEEPSEEK_API_KEY` 为过期 Key（401 AUTH）；设置页 YAML Key 正常已充值。已同步 User env；`is_running` 认 401 为存活；启动日志解析 `?token=` 写入 session `web_url`。  
**Harness 会话损坏（同日）**：`session-ec64…` seq gap → 误提 v3 → `SessionFormatUnsupported`；再因整文件单帧 zstd 导致 dsh 无法启动。已将健康内容降为 v0，并按 dsh 规范「首帧仅 header」重写；服务已起来。若该会话仍打不开，新建会话（备份在 `_corrupt_backup_*` / `_framefix_aside_*`）。  
**Harness 双路线四步开用（同日）**：未装时 SetupGate 选「官方精简 / 预制必备」→ 分阶段进度下载 zip → 一次 API Key → 检测启动；`harness_prefab` + `build_harness_prefab.py`；CDN URL 待填。  
**Harness 鉴权拒（2026-09-11）**：内嵌「dsh web authentication required」= 无 `?token=`。根因——① TOA 重启后 session URL 丢；② `setUrl` 破坏 token；③ 鉴权成功 303 后地址栏变裸 URL 被误判重开 → 死循环。已修：日志回补 token、`normalize_nav_url`、正文探测 cookie 就绪、失败分支与 READY 拆开。  
**Harness 小白原则（同日）**：主理人裁定——用户不懂技术，复杂配置是摆设；日常只走引擎页四步，系统设置 Harness 标「高级排障 · 日常勿改」（ARCH-05 §4.2）。  
**Harness 整改波次（2026-09-11）**：G0 live 启停修通过（无 WorkBuddy）；钉扎 `dsh@0.1.5-rc.1`；便携 Node；双包已上 `yczh.tech/downloads/harness-*-0.1.5-rc.1.zip`（nginx 已放行）；更多→升级运行时；设置页默认内嵌；ARCH-10 执行中，待干净机点验。  
**预制版构包（2026-09-11）**：已从本机 runtime 打出分离 CDN 双包至 `packaging/dist/harness/`（各 ~459MB）；**未**打进 TOA Setup（gitignore + release_config_guard）。  
**Harness CDN 发版自动化（同日）**：对标 Setup 两段式——`sync_portal_harness.ps1` 上传 → **主理人确认切配置** → `sync_harness_bundles.py --apply --verify-cdn`（SOP-04 §5）。当前新包待步 2 上传。  
**Harness 已装升级（同日）**：进页提示（更新 / 不更新 / 今日不提醒）→ 确认后更新 → **页示已升级完成并提示启动服务**；禁静默下大包。基础版白名单已含 `harness_agent`。  
**Harness cost-manager（同日晚）**：本地 link `@dachengge/dsh-cost-manager` 因 tool 无 output schema 启动注册失败拖死；已入 `_BOOT_KILLER_PLUGINS` 剔除并重启 `3082`（日志仅剩 skill-catalog）。  
**W1 screenshot_tool（2026-09-14）**：钉图 HiDPI 逻辑尺寸+锚点夹紧；loupe 逻辑取样/框选免全图 compose；热键 `QTimer.singleShot` 延后抓屏；`verify_screenshot_tool_gaps.py` 绿。主理人点验 gaps 仍留。  
**Harness 误报「修一下」（同日）**：有待更新时禁进页 auto_start；普通启败改「再启动」；工具栏「修一下」仅凭证锁/插件类 NEED_REPAIR；端口冲突不再直接 NEED_REPAIR。  
**Harness 外部实例（同日）**：本机已跑着且 HTTP 通 → **直接装入**；端口占用但未确认 → 条提示「识别到本机有 Harness」→ **刷新加载**（主）/ **更新环境**（次）/ 知道了；仅用户点「启动服务」才问是否接管重启。  
**版本对齐（2026-09-14）**：TOA `APP`/`update_manifest`/线上 stable 均为 **3.1.18**。Harness：仓库+shipped+本机配置+`MANIFEST` 程序包号统一 **0.1.5-rc.1.1**（CDN）；dsh 内核钉扎仍为 **0.1.5-rc.1**。门禁 `scripts/verify_version_align.py`（已挂 verify_all）。进页不应再因编号漂移逼更新。  
**Harness 状态衔接（同日）**：`ARCH-10` §3.4 / G7 / §8.10 — 可更新不得阻断启动；禁静默大包。  
**热键吞键修复（2026-09-14）**：双击 Ctrl 的 WH_KEYBOARD_LL 在 64 位下 `CallNextHookEx` LPARAM 溢出 → 回调异常返回 0 → **整机键盘被吞**。已修传参/兜底卸钩；`verify_global_shell` 冒烟。若仍异常：设置→热键→关掉「双击 Ctrl 唤起」。  
引擎管家 Hold。
**邮箱代理研判（2026-09-14）**：稳定 MVP 约 4–7 人周；不追企微；**专家组已 `approved`**（主理人不审 §3.5）；排队等 WIP 空位开轨；默认 `show:false`。  
**并行推进 + 统筹（同日）**：WIP≤3；T1 截图翻译 / T2 记事本 / T3 OCR 已开跑。  
**专家组裁剪（同日）**：按「好用实用 + 符合方向」评审未完成工作；结论落 PROD-01 **§0.6**。近程只点验/Wave★ 做强/看板；番茄钟·调图·通用生成·企微邮箱·媒体框选权重等 **剔除排期**。
**W2 剪贴板（2026-09-14）**：补隐私时段 UI+prefs 持久（进页不再强关）；`push_*` 隐私一律不入库（截图/OCR 旁路也拦）；搜索+来源过滤；页/速贴「送入记事」；`scripts/verify_clipboard_history.py` 绿。**gaps 未清**（待主理人点验）。
**未完成核实（同日）**：`scripts/verify_unfinished_inventory.py` → **done 16 / mvp 32 / Hold 4 / stub 1**；关键路径文件 OK。已修 **pomodoro show:false**（Hold 却开侧栏）。`screenshot_translate` 故意无菜单 → `audit_migration` 已豁免。近程闸仍是 **主理人点验**，非再开轨。
**侧栏收口 + 四象限状态看板（同日）**：非点验 `mvp` 侧栏 **收掉**；点验池（含 `email_client`）**推上**。`quadrant_tasks` 默认 **状态** 三列（待办/进行中/已完成）可拖拽，另保留四象限与日历。口径见 PROD-01 **§0.6 D**。
**任务管理 UX（同日）**：菜单改名「任务管理」；模式顺序 **状态→日历→四象限**；统一进度/优先级色义；任务说明 + **送入记事本** 传送门（右键/编辑框/日历侧栏）。
**引擎侧栏回推（同日）**：收口时误把 `harness_agent`/Pencil/Drawio 整组隐藏致顶栏「引擎」消失；已恢复显示（`engine_host_hub`/`comfyui_web` 仍隐）。
**任务管理辨识度（同日）**：顶栏改为「范围｜视图｜新建」分组；看板/日历/优先级命名；古铜主题 `info` 改回蓝色，待办列与进行中列色差拉开；列头①②③+副标题。
**任务双色轴（同日）**：进度蓝/橙/绿 与 优先级红/紫/青/灰 **互不混用**；三视图（看板/日历/优先级）同源；主题增 `violet`/`cyan`/`muted`。
**色轴克制（同日）**：一视图只突出列头/日历条一色；行内第二维改纯文字；去掉色名副标题与日历双色点；Figma 规范稿 https://www.figma.com/design/33i58DSzYVurs4JGLBUAjA
**任务三视图联动（同日）**：看板/日历/优先级共用筛选与选中焦点；日历条跟进度色（含已完成绿）；切视图保留同一任务高亮。
**桌面浏览回推（同日）**：侧栏收口误把 `column_preview` 隐掉；主理人反馈后恢复 `show:true`（点验池 · PROD-01 §0.6 D）。
**桌面紧凑布局（2026-09-16）**：工具栏路径框改为面包屑；快筛栏加文件名圆角检索；预览标题与源码/预览 Tab 同行，腾出垂直空间。
**桌面 Office 结构化预览（同日）**：Word→HTML 标题/加粗/表格；Excel→工作表切换+表格；PPT→分页卡片；后台线程解析；非原样排版，完整仍「打开」。`verify_office_structured.py` 绿。
**桌面视频首帧（同日）**：预览区抽视频首帧图（OpenCV/ffmpeg）；体积统一 B/KB/MB/GB（不再整文件只显示 KB）。`verify_video_poster.py`。
**桌面视频白屏修复（同日）**：首帧回调改 QueuedConnection 回主线程；贴图延后重试，避免点几次后「有元信息无画面」。
**主理人·记事排版（2026-09-15）**：TOA 提供好用工具，让用户自己轻松做出美观排版——**非预制内容堆观感**。已回写 `product.yml`、PROD-01/02。  
**主理人·记事三路径（同日）**：① 右侧拖入美观组件（拖入长啥样就是啥样，只改字）② 类 Word 自由排版 ③ 手写 Markdown 可选且同风格展示；**禁止 Markdown 学习门槛**。已回写 product.yml / PROD-01/02。  
**记事组件库落地（2026-09-15）**：设计默认 + 右侧 10 组件（点/拖插入）；页签改为设计→预览→源码；新建空白不塞范文；`verify_quick_notepad_gaps.py` 绿。待主理人点验 gaps。
**记事 Mermaid 预览（2026-09-15）**：本机 `mermaid.min.js`；图示组件改为可视框图（非代码墙）；预览经 `toa-mmd` 载荷出真图；文案已去外部教程品牌。
**主理人·图示真源（同日）**：不要 HTML/`toa-mmd` 加持；**图示正文=原生 Markdown ` ```mermaid `**；组件栏 HTML 仅缩略；插入后进预览出图。已改 component_blocks / page / verify。
**主理人·记事格式（2026-09-15）**：不做设计区 HTML 主路径；模式改为 **TXT / MD / HTML**（默认 MD）；编辑+预览；图示仍为原生 Markdown。已回写 product.yml / PROD-01。
**记事 MD 组件栏（同日）**：MD 编辑页恢复右侧拖拽组件；插入均为原生 Markdown（非 HTML 设计区）。
**记事组件预览验收（同日）**：34 项逐一 `setMarkdown`/Mermaid 预览断言绿；高亮改 HTML span 底色；图片占位补说明行；`scripts/verify_notepad_components.py`。
**记事拖入组件无效果（同日）**：MD 源码区/viewport 未 acceptDrops，松手被忽略；已开拖放并挂 viewport 过滤，页面级 MIME 回落。
**记事 HTML·H5（同日）**：HTML 格式右侧 H5 常规组件（顶栏/卡片/按钮等）；设计区拖拽所见即所得；网页预览手机壳；完整外部网页仍源码编辑。
**记事 H5 预览错位（同日）**：Qt toHtml 被当整页打开导致无手机壳/无单位 padding；改为抽 body + 净化 + 手机框预览。
**记事格式安全（同日）**：TXT/MD/HTML 分槽 `bodies`；切换先保留再恢复，禁止空覆盖；切格式时禁误用新格式 autosave 冲原文；`notes.json` 原子写+`.bak`。
**记事组件 code↔预览（同日）**：MD 34 + H5 18 逐项「生成代码→插入→解析预览」锚点一致；`scripts/verify_component_roundtrip.py`。
**记事产品模型（同日）**：模板/组件/工具/格式/模式五层关系写入 **PROD-01 §0.5.1**；同步 product.yml、PROD-02 §6.2、manifest gaps、research top3 指针。
**记事 MD 预览/高亮（同日）**：含 Mermaid 时误把 MD 当 HTML 整段甩源码 → 改为始终 setMarkdown；高亮组件改插 `==高亮==`（不再塞 span）。
**记事砍 HTML（同日）**：主理人裁定只保留 **TXT + MD**；去掉 HTML/H5 格式与强制跳预览；旧 HTML 槽只读迁出。已回写 PROD-01 §0.5.1 / product.yml / PROD-02 / manifest。
**记事组件卡（同日）**：组件库卡片按预览实际效果展示；拖入/点击仍插入 Markdown。
**记事 MD 三模式（同日）**：源码 / 设计 / 预览；工具栏·拖入·手写一律写 Markdown 源码再刷新设计；PROD-01 §0.5.1 已回写。
**记事组件三硬规（同日）**：①插入纯 MD 禁 HTML/空串 ②卡片=预览同口径 setMarkdown ③工具栏/拖入/手写同源；`verify_md_component_consistency.py`。
**记事去网页（同日）**：主理人确认无 HTML 面；组件卡不再用缩略 HTML；MD 预览取消 WebEngine/Mermaid 出图，一律 setMarkdown；拖拽 MIME 只带 MD。
**记事拖入文末+卡=预览（同日）**：组件点/拖一律插正文末尾；非图示卡走 refresh_markdown_preview；图示卡框图缩略 + 预览 Mermaid 出图。
**记事收口源码+预览（同日）**：主理人裁定去掉设计面；组件/工具栏/预览同源；砍 Mermaid·公式·假图片等半截组件，保留 14 个能预览的块。
**记事干净重构（同日）**：重写 `quick_notepad_page`（≤~1000 行）；删 `design_edit`/`h5_blocks`/`mermaid_preview`；抽出 `md_text`；顶栏去噪；桌面「导入记事本」按钮隐藏；四条 verify 绿。PROD-01 §0.5.1 已补「主路径少按钮 · 桌面传送门隐藏」。待主理人点验 gaps。
**主理人·记事一源三面（2026-09-16）**：废除「TXT格式=MD编码」混称；改为 **编码(txt)·设计(所见即所得)·预览**；工具栏=组件图；编码/设计均可拖入；**必须支持图片、真所见即所得**；外观对齐菜鸟教程文档感。专家组已回写 PROD-01 §0.5.1 / product.yml / PROD-02 §6.2 / manifest gaps。
**记事一源三面工程落地（同日）**：去掉 TXT|MD 下拉；默认 **设计**；`DesignTextEdit` + Markdown 一源往返；插图设计/编码均可；四条 verify 绿。待主理人点验 gaps。
**记事组件 18 项（同日）**：补删除线 / 行内代码 / 分割线；工具栏≡组件≡卡片≡预览由 verify 硬门禁保证（非整站克隆菜鸟教程）。
**主理人·记事收录原则（同日）**：TOA 纳入项 **不需与菜鸟一致**；只求 **好用·高频·常用，不贪多**。已回写 PROD-01 §0.5.1 / product.yml / PROD-02。后续扩组件须证高频缺口。
**记事手写 MD 预览（同日）**：编码面手写（无组件）切预览须正确解析；高亮展开避开代码围栏；verify 覆盖标题/列表/引用/代码/表/链/待办/高亮。
**记事取消设计面（2026-09-16）**：只保留 **编辑/预览**；组件库=标记全集；工具栏同源；`verify_quick_notepad_gaps` 等四条绿。
**记事内核体验（2026-09-29）**：参照 DartBinEditor Lite 体验标准：工具栏分栏；统一 `preview_pipeline`；`media_store` 分批落盘；编辑↔预览落点。
**记事所见即所得（同日）**：主理人要求「打开就像成品文档」的阅读态 + **所见即所得编辑**；预览改为纸面 Web 阅读态；落盘仍 Markdown。已回写 PROD-01 §0.5.1 / product.yml / PROD-02 / manifest gaps。剪藏/多页签/主题包未做。待主理人点验 gaps。
**记事预览对标（同日）**：预览不再沿用 Qt 行内样式；纸面接管标题层级、引用条、提示块、待办框、表头、代码块与图表框。颜色仍跟当前主题。
**记事组件原样解析（同日）**：在录 27 项阅读态按语义还原（加粗/斜体/删除线/行内代码/高亮/围栏换行/图表）。`verify_quick_notepad_gaps` 绿。待主理人点验 gaps。
**记事借鉴 WPS（2026-09-30）**：主理人要求提升写作能力。已加源码页签、效率指南、导入 Markdown。公式与另存 Word 未做。
**记事三面对齐（2026-09-30）**：主理人要求预览、编辑、源码对齐。未改编辑面时原文逐字保留；改过之后三面和落盘锁同一串 Markdown。待主理人点验 gaps。
**撤回微信嵌窗（2026-09-30）**：主理人：嵌窗没法用，不要这功能。要的是办公助手支持在线沟通，不是把微信窗口嵌进主区。已删 `wechat_host`；方向写入 PROD-01 §2「建议不做」。
**记事图表进组件库（同日）**：「图表」分组集中 Mermaid（流程 TD/LR · 时序 · 饼图 · 甘特）；拖入编辑窗；预览本机 `mermaid.min.js` 出图；不上工具栏挤占。
**记事组件卡给样子（同日）**：常用卡=预览同口径渲染；图表卡迷你示意图；图片卡占位示意；tip「卡片=拖入后的样子」。
**记事图片/图标可调大小（同日）**：组件拆「图片/图标」；插入弹窗选显示大小（小图标48·小160·中360·大560·宽720·原图）；默认按像素建议并记忆；源码落 `<img width>`；预览钳过大图。
**记事侧栏检索+级联删（同日）**：搜索框移到左侧记事栏顶；删除父记事同时删全部子孙（确认文案提示条数）。
**Harness 插件被洗空（2026-09-15）**：升预制 `0.1.5-rc.1.1` 时 `_ensure_profile_flavor` 把空 `prefab_essential_plugins` 当成白名单过滤 → 本机 15 插件冲成仅核心；`last_good` 也被标成洗后态。已从快照 `20260914_095729_987655` 恢复并改指针；代码改为预制升级**保留用户 bundles**；ARCH-10 §3.4.3 增「不洗用户插件」。**请重启 Harness 服务**验证插件回来。
**MXAPI 接入模型管理（同日）**：`model_catalog` 增 `mxapi_nano_banana_2` / `gpt_image_2` / `nano_banana_pro`（`open.mxapi.org/v1`）；Key 自动认 Harness `MXAPI_API_KEY`；三卡共用密钥。
**MXAPI 写入 DSH（同日）**：凭据补 `MXAPI_OPENAI_BASE_URL=/v1`（生图）+ `MXAPI_BASE_URL=/api/v2`（余额）；`$DSH_HOME/skills/image-generation` 与 AGENTS.md 改为 MXAPI 优先；**不**进 llm-pi-ai「模型」页（非对话模型）。
**壳·Ctrl+Tab 切主菜单（2026-09-21）**：`Ctrl+Tab` / `Ctrl+Shift+Tab` 循环顶栏一级子模块；事件过滤拦 Tab 焦点占用 + ApplicationShortcut 兜底；配置 `hotkeys.next_domain` / `prev_domain`。
**Harness 侧栏预览（2026-09-22）**：根因=Qt 未注册 `dsh-resource` → JS URL hostname 空 →「文件资源服务不可用」（浏览器正常）。已在 QApplication 前 `registerScheme(Syntax.Host)`；`verify_dsh_resource_url_scheme` 入 verify_all。重启 TOA3 后内嵌可预览。
**Harness 备份系统 + 内核漂移提示（2026-09-24）**：本机 dsh 被手动升到 `0.1.7-rc.1`（偏离钉扎 `0.1.5-rc.1`），「修一下」救不了。已加：更多/环境维护「备份系统」与版本对照；更新环境前自动备份；内核漂移进页提示「更新」恢复钉扎包；`verify_harness_system_backup`。请先备份再点「更新环境」。
**Harness 升级保插件（同日）**：安装/更新环境装前快照 bundles+deps，装后合并并重装缺失 registry 包；denylist（如 cost-manager）仍剔除。门禁扩 `verify_harness_simple_setup`。
**Harness 升级卡死解堵（同日）**：① 升级前整树备份含 `node_modules` 像卡死 → 改为跳过可重建的 `node_modules`/`node`；② `dsh-vision-router` / task-board 等 `settingsScope` → denylist；已剔并重启服务可用。请再点「更新」回钉扎内核。
**Harness 更新不卡窗（同日）**：根因=`_run_bg`→`run_safe` 在 UI 线程同步备份。改为 QThread 后台备份+下载；UpgradeStrip 进度条/取消；可切其它功能页。
**侧栏恢复扩展/定时任务（同日）**：`user_extensions` / `job_scheduler` 曾因点验池收口 `show: false`；主理人要回 → 已改 `show: true`（系统组）。
**Harness 更新后起不来（同日续）**：根因三件——① 便携 Node **22.14** 无 `createZstdCompress`（会话插件要 ≥22.15）；② `@opentelemetry/otlp-transformer` 缺 `logs/`；③ `dshmarket` undici 残缺。已升本机便携 Node→**22.22.0**、补齐 otel、denylist `dshmarket`；新增 `harness_runtime_heal` 启动前自愈；`is_running` 不再把 404 当就绪。本机 3082 已带 token 拉起。下次重建 prefab 须内嵌 Node≥22.15。
**Harness 内嵌≠浏览器（同日）**：会话数据未丢（浏览器可见工作区树）；内嵌空白侧栏多为 WebEngine Cookie/入口未带 token。已：强制持久 Cookie、桌面 Chrome UA、刷新一律 `force_navigate(token URL)` 清 HTTP 缓存。需**重启 TOA** 后再点「刷新」。
**Harness 费用管理 + 中文（同日）**：cost-manager 曾因无 `output.schema` 进 denylist→面板消失；本地包已补 `output.{schema,render}`，移出 denylist 并重启；`settings.yaml` 写 `locale.preference: zh`；WebEngine `Accept-Language: zh-CN`。`/cost` `/board` 已 200。用户需**重启 TOA** 再刷新内嵌。
**Harness「请更新到 0.1.2」误报（同日）**：本机内核已是 **0.1.5-rc.1**；弹窗来自 `dsh-context` 误读到 pnpm 里残留的 `dsh-session@0.1.0-rc.8`。已卸掉 `dsh-context`（非必要）并恢复服务；真要升内核走编码智能体「更新环境」。点「知道了」即可，**无需**按弹窗升版。
**Harness 升核 0.1.7-rc.2（2026-09-28）**：代码钉扎 `DSH_PINNED_VERSION=0.1.7-rc.2`；新增 `upgrade_dsh_core_inplace`（npm 原地升核，保留 `.dsh`+插件合并）；「更新环境」内核落后时走 npm 不重下整包。CDN zip 底座暂仍 0.1.5-rc.1.1（新装解压后自动对齐钉扎）。本机已升核并启动；费用管理保留；denylist 含 vision-router / task-board / dshmarket / dsh-context。请**重启 TOA** 后刷新。
**发版待点按钮 v3.1.23（同日）**：直链 200 · https://www.yczh.tech/downloads/TOA3-Setup-v3.1.23.exe ；运营台已预登记（`is_current=false`）。**主理人只点「设为当前」** → Agent 再 `--from-live --require-match --commit`。
**Harness denylist 复测移出 dshmarket / dsh-context（2026-10-07）**：核已钉扎 `0.1.7-rc.2`，两条原始理由复测均不成立——① `dshmarket` 原理由「undici@7.29.0 缺 `lib/cache/memory-cache-store`」，实测 `dshmarket@1.66.9 → undici@7.30.0`，`lib/cache/` 下 memory / sqlite 两个 store 均在；② `dsh-context` 原理由「版本探针误读 peer 为 `0.1.0-rc.8` 弹假升级门」，实测 profile 内 `dsh-session` / `dsh-settings` 均为 `0.1.7-rc.2`，`peer >=0.1.5-rc.1` 对齐。已从 `services/harness_plugins.py` `_BOOT_KILLER_PLUGINS` 移出两键（原样注释留证 + 复现命令），剩 3 键（agent-teams / vision-router / task-board）。复测：`dsh --profile web --dump-config` exit=0 无 `did not activate`；实启 3082 侧 `dsh-context` 导入失败已随降级 `0.49.1` 消除。模拟 `_dep_keepable` 判定 15 bundle 全保留。
**Harness profile 插件清单恢复（同日）**：`~/.toa3/harness-runtime/.dsh/profiles/web/package.json` 曾被历次 `*-before-repair-*` 修复削到只剩 3 个 `@dachengge` link，而 `pnpm-lock.yaml` 完整保留 11 项声明。按 lock 补回 8 项（skill-explorer / archify / config-manager / ffmpeg / notifier / ppt-master / preview / skillhub）+ dshmarket / dsh-context，`pnpm install --prefer-offline` 复用本地 store（reused 133 / downloaded 0）。现 13 bundle 全绿。备份 `profiles/_backup_before_plugin_restore_20261007/`。
**video-checker 追平 link/file 依赖判定（同日）**：该仓库 9/16 由 TOA3 脚手架分叉，`harness_plugins.py` 停在该日版本，缺 `_dep_keepable` / `_link_dep_target`，且无 `harness_dsh_launch.py`（故不能整文件覆盖）。已精确移植两函数 + `sanitize_web_profile_package` 两处判定（link 目标存在即保留，未进 bundles 时补回），`py_compile` 通过。该分叉与本机 profile 同一 `dsh_home`，属实际风险面。备份 `services/_backup_harness_plugins_20261007.py`。
**门禁夹具同步（同日）**：`verify_harness_simple_setup.py` L201-210 原以 `dshmarket` 作 denylist 夹具，移出后断言必崩（已复现 AssertionError）。改用仍在 denylist 的 `dsh-vision-router`，断言语义不变；`verify_all` 该项恢复绿。
**CDN 证书（2026-10-12）**：`www.yczh.tech` TLS 已恢复（HTTPS 200）；原「证书过期挡 verify」遗留关闭。

---

## 2. 下一待办

### 2.1 并行轨板（直开收口 · 专家组裁剪后）

| 轨 | 状态 | 说明 |
|----|------|------|
| W1–W5 / 翻译/记事本/OCR/邮箱 | **done-轨道** | 代码已交；**待主理人点验** |
| 四象限状态看板 | **已推** | 默认状态视图；待点验 |
| **近程只准** | 点验缺陷修复 + Wave★ 做强 + 看板串链 | 见 PROD-01 **§0.6** |
| **停手** | pomodoro/image_adjust/generic_generator/企微邮箱/媒体框选权重/… | §0.6 B 剔除；禁止再开凑数轨 |

- [x] **专家组裁剪**：PROD-01 §0.6 已落；剔除无必要计划  
- [x] W1–W5 / 翻译/记事本/OCR/邮箱 代码轨收口  
- [x] **未完成清单核实**（manifest×菜单×关键路径；番茄钟已隐藏）  
- [x] **侧栏收掉非点验 mvp；点验池推上 TOA**（§0.6 D）  
- [x] **四象限 · 状态看板**（待办/进行中/已完成）  
- [x] **商业发行 P0 工程收口**（2026-10-12）：release 日志/授权护栏/侧栏/诚实说明/`verify_license_gate`  
- [ ] **主理人点验池**（唯一近程产品闸）：Wave★ + 换装/招聘/看板 + 邮箱/翻译/OCR/记事本（Wave F 侧栏暂隐至点验）  
- [ ] **SOP-04 商用冒烟人工 1–5**（自动项见 `commercial_smoke_checklist.py`）  
- [ ] **确认运营台 3.1.23 已设当前** 后 Agent `--from-live --require-match --commit`  

机读任务：同目录 `collab_tasks.json`。

```powershell
python scripts/seed_collab_tasks.py --edition both --wipe-collab
```

---

## 3. 本轮备忘

| 项 | 说明 |
|----|------|
| 更新 | 2026-10-26 · **主理人裁定：发版安装包改传 `toa-service.yczh.tech/downloads/`** |
| 改了哪些 | 线上 nginx `toa-service.conf` 加 `/downloads/`（alias `/opt/toa-cloud/downloads/`，目录首页 302 官网下载页；备份在 `/root/toa-service.conf.bak.downloads-*`）；3.1.24 已硬链接过去试链 200；`sync_portal_installer.ps1`（exe 改传新目录 + HEAD 校验）· `prepare_ops_release.py` · 运营台 `admin/app.js|html`（已上线）· `scripts/sync_release_version.py` 默认直链；SOP-04 直链约定 · STD-01 B6 · packaging Skill 回写 |
| 不变 | `download_page` 仍官网 `www…/downloads/`；≤3.1.24 已登记直链不回改；Harness CDN 仍走 www |
| 更新 | 2026-10-12 · 商业发行验收整改 + **SOP-08 Skill** |
| 改了哪些 | 同上波整改；新增 `docs/规范/SOP-08-商业发行验收.md` · Skill `toa3-sop-commercial-release`；挂入 00清单 / toa3-dev-suite / STD-01 / SOP-04·07 / OPS |
| 待主理人 | Wave★ 点验清 gaps；商用冒烟人工项；确认设当前版后吩咐 sync commit |
| 更新 | 2026-10-07 · Harness denylist 复测移出 + profile 插件清单恢复 |
| 改了哪些 | `services/harness_plugins.py`（denylist 减 2 键）；`profiles/web/package.json`（+10 插件）；`scripts/verify_harness_simple_setup.py`（denylist 夹具 dshmarket→dsh-vision-router） |
| 核实结果 | 15 bundle 全绿；`--dump-config` exit=0 无 `did not activate`；`verify_all` 仅剩 2 项环境失败（CDN 证书过期） |
| 待主理人 | 启动 TOA3 后确认「已移除拖死/无法解析的插件」提示消失 |
| 旁支 | video-checker 同名文件已精确移植 `_dep_keepable` / `_link_dep_target`（不整文件覆盖，因缺 `harness_dsh_launch`） |
| 更新 | 2026-09-14 · 侧栏点验收口 + 四象限状态看板 |
| 核实结果 | done16 / mvp32 / Hold4 / stub1；Hold 侧栏已对齐隐藏 |
| 侧栏 | §0.6 D：非点验 mvp 收掉；邮箱等点验池已推上 |
| 四象限 | 默认「状态」三列；可切四象限/日历 |
