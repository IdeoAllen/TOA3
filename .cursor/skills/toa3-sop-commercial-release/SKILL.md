---
name: toa3-sop-commercial-release
description: >-
  TOA3 SOP-08 商业发行验收：A10.4 硬闸、商用冒烟、侧栏收口、授权护栏、Wave★ 点验与对外话术。
  Use when 正式发行、商业验收、可商用、设当前版前验收、A10.4、商用冒烟、发行整改、上线发行.
---

# SOP-08 · 商业发行验收（Skill）

**正文**：`docs/规范/SOP-08-商业发行验收.md`  
**标准**：STD-01 · **A10.4** · A8 · A9 · B6  
**关联**：SOP-04 打包五步 · SOP-03 模块点验 · ARCH-04 · PROD-01/02 · OPS-01  
**详表**：[`references/checklist.md`](references/checklist.md)

## 触发后立刻做

1. **读正文 SOP-08**，按 §3 摸底 → 输出验收表（工程 / 产品 / 商务 / 授权 / 综合）。  
2. **未过 A10.4** → 裁定「暂缓正式发行」；允许内测/预发话术，禁止称可商用当前版。  
3. 按 P0 → P1 → P2 整改；**禁止**假清 Wave★ gaps、假标 `done`。

## 必跑命令

```powershell
python scripts/verify_all.py
python scripts/commercial_smoke_checklist.py
python scripts/verify_license_gate.py
# 主理人设当前版之后：
python scripts/sync_release_version.py --from-live --require-match --commit
```

## 硬禁令（摘要）

- A10.4 六项未齐 → 禁止设当前版 / 称可商用  
- 生产：`skip_login` / `dev_grant_all` / `allow_dms_fallback` 必须关  
- 发版说明必须写 Wave★/激活需网等已知限制（SOP-04 §2.1）  
- 进度只写 OPS-01；规范意见回写 SOP-08 / STD / PROD（SOP-07）

## 与打包 Skill 分工

| 用户说 | 加载 |
|--------|------|
| 打包 / 上传 / 设当前版 | `toa3-sop-packaging` |
| 商业验收 / 正式发行 / 能不能卖 | **本 Skill**（必要时再调 packaging） |
