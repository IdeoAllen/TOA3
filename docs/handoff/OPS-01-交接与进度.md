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
| 写码门禁 | 产品亮点研究 + 恰好 3 条不落俗套独到处，主理人确认后再写业务码（SOP-01 / STD-01 B1.1） |
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

**v3.1.12** 已发（Portal 上传 + 运营台当前版；`eec70f3` 版本对齐已提交）。  
**v3.1.11** 已发；壳层固若金汤已收口。  
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
引擎管家 Hold；Harness 无感就绪仍为主线之一。

---

## 2. 下一待办

- [ ] **快速记事点验**：Ctrl+V 插图可见；拖角缩放不闪、不扯乱上下文；段距/行距/空段
- [ ] **助教打卡换装点验**（Agent 不得代清 gaps）：张数对齐；水印仍在仅服装变；旁路输出；单张失败不堵批
- [ ] **助教招聘稿点验**（Agent 不得代清 gaps）：示例班名城市/天数/费用；生成并复制一致；改日薪固定段不变
- [ ] **培训交付看板点验**（Agent 不得代清 gaps）：绑定后串链根目录/名单；无 DMS/无 OAuth 粘贴开跑；打开文档与清除会话
- [ ] Wave★ / Wave F **主理人点验**清 gaps
- [ ] Harness：装插件前可「备份当前配置」；搞挂后「修复运行环境」或「恢复上次可用配置」；点验日志/卸载
- [ ] Harness 无感就绪；达标前禁 Hub 半残 UI

机读任务：同目录 `collab_tasks.json`。

```powershell
python scripts/seed_collab_tasks.py --edition both --wipe-collab
```

---

## 3. 本轮备忘

| 项 | 说明 |
|----|------|
| 更新 | 2026-09-10 · **v3.1.12** Setup 已出 |
| 规范 | STD-01 B1.1：research=挖亮点不落俗套；短规则 mdc 已同步 |
| 口径 | DMS 可售专业系统；TOA freemium；看板不进 `local_free` |
| Harness | 默认内嵌呈现；揭罩切到 WebView 修闪/假死；浏览器为可选 CTA；点按反馈+刷新 |
| 本轮落地 | 桌面浏览 Markdown：**源码 / 预览**双模式；预览①只滚②③调宽；导入记事本跟踪落点 |
| 发版 | **v3.1.12** 完成：stable = APP_VERSION = update_manifest；直链可用 |
| 发版直链 | https://www.yczh.tech/downloads/TOA3-Setup-v3.1.12.exe |
| 验收 | 记事本新增 gaps 待点验 |
| 验收 | Harness 已重启可用；换装/招聘/看板 gaps 仍待点验 |
