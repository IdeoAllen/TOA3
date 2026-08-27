---
name: toa3-add-feature
description: >-
  TOA3 添加或增强功能的标准流程：Top3 对标、与主理人共创 3 个独到之处、
  架构/性能/品质门禁、菜单与控件库落地、验收与 migration 回写。
  Use when adding a new TOA3 module, enhancing an existing feature, migrating
  from TOA2, or when the user says 新功能/做强/开工/迁移模块.
---

# TOA3 · 添加 / 增强功能

在 TOA3（PySide6）中**新增或做强**任一功能时，按本 skill 执行。禁止跳过门禁直接写码。

**交接总册（愿景/规则/要求）：** `docs/handoff/HANDOFF_INDEX.md`  
**当前进度：** `docs/handoff/AGENT_RELAY.md`

## 何时使用

- 用户说：新功能、做强、开工、迁移某模块、完善已有页  
- Wave★ 八件套任一项、或培训线模块  

## 强制顺序（不可跳）

### 0. 读约束

- `.cursor/rules/toa3-feature-top3-research.mdc`  
- `.cursor/rules/toa3-feature-acceptance.mdc`  
- `.cursor/rules/toa3-control-library.mdc` / `toa3-architecture-layers.mdc`  
- `docs/功能清单与优先级.md`  
- `docs/architecture/14-超边门禁与目标锁定.md`（超边判定 · 合入自检）  

### 1. 定场景（与主理人对齐）

写清：谁 / 何时 / 输入 / 输出 / 失败提示。

### 2. Top3 + 三独到处（共创）

1. 复制 `docs/research/_TEMPLATE-top3.md` → `docs/research/<module_id>-top3.md`  
2. 填 Top3 对标与取长补短  
3. **草案 3 条独到之处** → 与主理人逐条论证 → 勾选「主理人已确认」  
4. 文档 `approved` 前 **禁止** 写业务实现  

### 3. 技术方案一页纸（同文档 §4）

- 栈 / 否决项  
- 落点：`modules/<id>/` + `services/` + 必要时 `integrations`  
- 性能：热键/进页不阻塞；HiDPI 若涉截图/自绘  
- 品质验收：可测步骤（含兑现 3 条独到处）  

### 4. 实现清单

| 项 | 要求 |
|----|------|
| 页面 | `BasePage`；控件只用 `widgets/` |
| 菜单 | `config/app.yml` menu_items；`menu_registry.MIGRATED_MODULES` |
| 存储 | `config/storage.yml` + `storage_paths` |
| 清单 | `migration_manifest.yml`：`mvp` + gaps；未验收勿 `done` |
| 密钥/三方 | 仅 `services/integrations` + secrets |
| 弹窗 | `BaseDialog` / `FormEditDialog`（必须主题化，禁止裸 QDialog） |
| 关于 / 账号 | 顶栏弹窗 `AboutDialog` / `UserProfileDialog`，不做侧栏页 |

新建页可先占位，但须在 manifest 标 `stub`/`mvp`，不得假绿灯。

### 5. 自测与联调

```powershell
cd TOA3
python scripts/audit_architecture.py
python scripts/audit_migration.py
python scripts/verify_all.py
python -m app.main
```

- 主理人点验；问题写入 `gaps`  
- Windows 强杀重启 exit `4294967295` 可忽略  
- 合入前过超边自检（见 architecture/14）  

### 6. 收尾

- [ ] research 文档 `approved` 且三独到处已确认  
- [ ] gaps 清空或仅保留明确「后续增强」并降为 mvp  
- [ ] 仅当主理人认可「每天愿意用」才标 `done`  
- [ ] 更新 `docs/迁移进度.md` 一句摘要（若该波次有变）  

## 反例

- 未共创 3 独到处就写 UI  
- home/shell 写死入口  
- 打开设置就联网 health_check  
- 有 gaps 仍标 done  
- 截图层不管 DPR 导致「默认放大」  

## 参考路径

| 用途 | 路径 |
|------|------|
| 优先级 | `docs/功能清单与优先级.md` |
| Top3 模板 | `docs/research/_TEMPLATE-top3.md` |
| 超边门禁 | `docs/architecture/14-超边门禁与目标锁定.md` |
| 迁移状态 | `config/migration_manifest.yml` |
| 模块规范 | `docs/architecture/06-业务模块规范.md` |
| 交接 | `docs/handoff/HANDOFF_INDEX.md` · `AGENT_RELAY.md` |
