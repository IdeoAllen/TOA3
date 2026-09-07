# OPS-01 · Agent 交接与进度

> **编号**：OPS-01 · 进度唯一文件  
> **规范入口**：`docs/规范/00-规范清单.md` · Skill：`toa3-dev-suite`  
> 更新：2026-09-07

---

## 0. 开场

| 问 | 答 |
|----|----|
| 产品 | 运营宝 / TOA3，PySide6 桌面办公套件 |
| 只改哪 | 只改本仓库 TOA3；TOA2 封板 |
| 写码门禁 | Top3 + 恰好 3 条独到处，主理人确认后再写业务码（SOP-01） |
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

**v3.1.11** 已发；壳层固若金汤已收口。  
桌面端职能已裁定：收录 + 生命周期 Host；重活浏览器；**费用不做**。  
引擎管家 Hold；主线 **Harness 无感就绪**。  
DeepSeek Harness：hoist 检测与脏插件清理后，本机可启 `http://127.0.0.1:3082`。  
**文档**：已建成并 **全面上线**「00 规范清单 + STD + SOP + Skill」；旧标准/流程已 `_archive/OFFLINE`。  
主理人后续意见 → 强制回写 STD/SOP（A0.7 / SOP-07）。

---

## 2. 下一待办

- [ ] Wave★ / Wave F **主理人点验**清 gaps（Agent 不得代清）
- [ ] Harness 三步开用点验；密钥以设置页为准（慎用本机 `DEEPSEEK_API_KEY` 盖住设置页密钥）
- [ ] Harness 无感就绪（预置包 / 官方安装器 / Agent 代装择一）；达标前禁 Hub 半残 UI
- [ ] 发版外 WIP 分批提交（主理人定）

机读任务：同目录 `collab_tasks.json`。导入四象限：

```powershell
python scripts/seed_collab_tasks.py --edition both --wipe-collab
```

开发版与正式版数据目录不同；绿标「正式版」须 seed 到 release 路径。

---

## 3. 本轮备忘

| 项 | 说明 |
|----|------|
| Harness Web | vendored 认 npm hoist；sanitize 去掉无法解析的 dshmarket 等 |
| 引擎管家 | Hold · 菜单 `show: false` |
| 文档治理 | **新规范全面上线**：旧标准/流程已 `_archive/OFFLINE`；只认 `docs/规范/00`+STD/SOP+ARCH/PROD/OPS；主理人意见强制回写规范（A0.7 / SOP-07） |
