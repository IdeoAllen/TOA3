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
| 写码门禁 | 产品亮点研究 + 恰好 3 条不落俗套独到处，经 **专家组** `approved` 后再写业务码（主理人 **不审** §3.5；点验仍属主理人） |
| 完成 | `migration_manifest` gaps 空且主理人认可才 `done` |
| 进度 | **只改本文（OPS-01）** |
| 排期 | `docs/PROD-01-功能清单与优先级.md` |
| 产品话术 | `docs/PROD-02-商务产品手册.md`；运行时 `config/product.yml` |
| 工程标准 | `docs/规范/STD-01-工程标准与流程.md` |

**Skill 全套**：`toa3-dev-suite`（入口）· `toa3-sop-new-feature` · `toa3-sop-theme-control` · `toa3-sop-module-accept` · `toa3-sop-quality-pipeline` · `toa3-sop-packaging` · `toa3-sop-debug-crash` · `toa3-sop-user-extension` · `toa3-sop-docs-handoff`

```powershell
python scripts/verify_all.py
python -m app.main
```

---

## 1. 一句话现状

**v3.1.18** 已发：stable = APP = update_manifest；直链可用；**更新说明已补写**（发布时曾留空，已入库并门禁：设当前版必须填说明）。  
直链：https://www.yczh.tech/downloads/TOA3-Setup-v3.1.18.exe  
说明：全局介入档案与配置点：双击Ctrl唤起、拖入开桌面、沉浸全屏(F11)、退出/托盘均可配置；发版说明与版本对齐流程标准化。  
对齐提交：`699ce72`（manifest）+ 扩白名单后补交壳/热键/ARCH-11（见最新 `release: TOA3 v3.1.18`）。  
**发版提交口径**：上传脚本自动 commit 多数跳过；**设当前版后 Agent 必须再跑** `--from-live --require-match --commit` 并回报 hash。  
**全局介入档案**：`ARCH-11` + `global_shell_features` + `verify_global_shell`；Mac 仅口径。  
**v3.1.17** 热键/预览；**v3.1.16** Harness CDN；**v3.1.14** 图片预览。
**双产品商业**（已回写）：DMS=专业高门槛可售；TOA=免费钩子+高级付费；腾讯文档轻量轨；并行不强绑。  
**培训交付看板** `training_delivery_board`：**mvp 已落地**（业务侧栏 order=5，需授权）；班级 handoff + 串链六环；亮点研究 `approved`。待主理人点验清 gaps。  
**助教招聘稿** `assistant_recruit_post`：**mvp 已落地**（业务侧栏 order=45）；命名即表单 + 话术锁定 + 复制即发；research `approved`。待点验清 gaps。  
**助教打卡换装** `assistant_outfit_swap`：**mvp 已落地**（业务侧栏 order=46）；目录全量 + 着装预设 + 只换服装保水印；经 image_gen 编辑；research `approved`。待点验清 gaps。  
**Harness（2026-09-10）**：`@nanmicoder/dsh-agent-teams` 依赖缺失 `uiConversation` → Failed to load plugins；已剔除并重启 `3082`；新增 profile **配置快照/恢复上次可用**（编码智能体 → 更多）；sanitize denylist。  
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
**Harness 误报「修一下」（同日）**：有待更新时禁进页 auto_start；普通启败改「再启动」；工具栏「修一下」仅凭证锁/插件类 NEED_REPAIR；端口冲突不再直接 NEED_REPAIR。  
**Harness 外部实例（同日）**：本机已跑着且 HTTP 通 → **直接装入**；端口占用但未确认 → 条提示「识别到本机有 Harness」→ **刷新加载**（主）/ **更新环境**（次）/ 知道了；仅用户点「启动服务」才问是否接管重启。  
引擎管家 Hold。  
**邮箱代理研判（2026-09-14）**：稳定 MVP 约 4–7 人周；不追企微；**专家组已 `approved`**（主理人不审 §3.5）；排队等 WIP 空位开轨；默认 `show:false`。  
**并行推进 + 统筹（同日）**：WIP≤3；T1 截图翻译 / T2 记事本 / T3 OCR 已开跑。  
**专家组（同日续）**：写码过门改为 **B10.1 专家组审 §3.5**；主理人只点验 / 设当前版。已回写 STD/SOP-01/模板/短规则。  
**专家组论证并行制度（同日）**：四席修订后通过（WIP/所有权/冻结/升显/冒烟等）。

---

## 2. 下一待办

### 2.1 并行轨板（WIP≤3 · STD-01 B9 · 2026-09-14 开跑）

| 轨 | module | 状态 | 独占路径 | 本轮目标 |
|----|--------|------|----------|----------|
| **T1** | `screenshot_translate` | **doing** | `services/screenshot_translate*.py`；截图工具栏挂点（只读协调） | Top3 已 approved；做强 OCR→对照→译→复制；补 verify；manifest `missing`→`mvp` |
| **T2** | `quick_notepad` | **doing** | `modules/quick_notepad/**` | 自测加固 Ctrl+V 插图/拖角缩放/PDF/HTML；**不代清**主理人点验 gaps |
| **T3** | `ocr_tool` | **doing** | `modules/ocr_tool/**`（若有）+ 截图 OCR 相关 services | 中文引擎评估与安装引导（manifest gap） |
| **排队** | `email_client` | **ready**（专家组已 approved） | 待插入：`modules/email_client/**` · `services/mail/**` | WIP 满 3；下一空位或让出 T3 后开跑；默认 `show:false` |
| **点验池** | 换装/招聘/看板/Wave★ 多项 | blocked | — | **仅主理人**；Agent 不代清 gaps |

- [x] **并行开跑**：T1/T2/T3 登记如上  
- [ ] **邮箱轨**：专家组已 `approved`；等 WIP 空位开跑（或主理人点名让出一轨）  
- [ ] **快速记事点验**：Ctrl+V 插图可见；拖角缩放不闪、不扯乱上下文；段距/行距/空段  
- [ ] **助教打卡换装点验**（Agent 不得代清 gaps）：张数对齐；水印仍在仅服装变；旁路输出；单张失败不堵批  
- [ ] **助教招聘稿点验**（Agent 不得代清 gaps）：示例班名城市/天数/费用；生成并复制一致；改日薪固定段不变  
- [ ] **培训交付看板点验**（Agent 不得代清 gaps）：绑定后串链根目录/名单；无 DMS/无 OAuth 粘贴开跑；打开文档与清除会话  
- [ ] Wave★ / Wave F **主理人点验**清 gaps  
- [x] Harness 自动化交付：默认沙箱干净机（13082）+ 契约；**不**动用户 3082/`~/.toa3`；`--live` 才碰本机  
- [x] Harness CDN URL/sha256 已填且探测可达；诊断包已落地；BOM 自清  
- [x] Harness CDN：`0.1.5-rc.1.1` 已上传并切 yml（官方 `0d655f2e…` / 预制 `8b50ba65…`）  
- [ ] **运营台设当前版 v3.1.18** 后：`python scripts/sync_release_version.py --from-live --require-match --commit`

机读任务：同目录 `collab_tasks.json`。

```powershell
python scripts/seed_collab_tasks.py --edition both --wipe-collab
```

---

## 3. 本轮备忘

| 项 | 说明 |
|----|------|
| 更新 | 2026-09-14 · **写码过门改专家组**（主理人不审 approved） |
| 规范回写 | STD-01 B1/B10.1；SOP-01；模板；短规则；email_client → approved |
| 专家组 | §3.5 主审；主理人只点验 / 设当前版 |
| 邮箱 | 专家组已通过；排队等 WIP |
| 统筹角色 | 本会话：质量/进度/发版/全局；WIP≤3；升显权在统筹 |
| 发版 | **v3.1.18** Setup 已上传；**等运营台设为当前版**；对外须过 A10.4 |
| 发版直链 | https://www.yczh.tech/downloads/TOA3-Setup-v3.1.18.exe |
| Harness CDN | https://www.yczh.tech/downloads/harness-{official,prefab}-0.1.5-rc.1.1.zip |
| Harness 升级 | 进页：更新 / 不更新 / 今日不提醒；完成后「已升级完成」→ 启动服务 |
| 待主理人 | ① 运营台设当前版 v3.1.18；② Wave★/换装/招聘/看板**点验**（不审 research） |
| 验收 | 记事本新增 gaps 待点验 |
| 验收 | Harness 已重启可用；换装/招聘/看板 gaps 仍待点验 |
| 主理人意见 | 能力接入堆 Harness 不伦不类 → 三轨：系统/引擎页/扩展；环境维护人话收拢 |
