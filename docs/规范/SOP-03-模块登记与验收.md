# SOP-03 · 模块登记与验收

> **编号**：SOP-03 · **Skill**：`toa3-sop-module-accept`  
> **质量深化**：`toa3-sop-quality-pipeline`  
> **依据**：STD-01 · B4 · B5 · A9 · A10

## 1. 登记检查表

- [ ] `modules/<id>/`（`BasePage`）  
- [ ] `config/app.yml` 或 `data/user/menu.yml` → `menu_items`  
- [ ] `MIGRATED_MODULES` / `module_loader` 可 import  
- [ ] `config/migration_manifest.yml`（status + gaps）  
- [ ] 有落盘 → `config/storage.yml`  
- [ ] `python scripts/audit_migration.py`  

## 2. 验收流程

1. （建议）跑 `toa3-sop-quality-pipeline` 生成用例地图（产出不进 `docs/` Excel）  
2. `python scripts/verify_all.py`  
3. `python -m app.main`；强杀码 `4294967295` 可忽略  
4. 主理人点验 → 写/清 `gaps`  
5. 合入前过 ARCH-03 超边自检  

## 3. 完成灯

| 状态 | 条件 |
|------|------|
| `done` | 可用且 gaps 空且主理人认可 |
| `mvp` | 有缺口或未点验 |
| 禁止 | 有页面就标 done；Wave★ 未过 Top3 标 done |

## 4. 可见性

侧栏：`show: true` + manifest + license；未验收勿盲目露出。
