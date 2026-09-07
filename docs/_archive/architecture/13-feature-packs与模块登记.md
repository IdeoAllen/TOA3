# Feature Packs 与模块登记

> 一页纸：新能力如何接入 SKU、菜单与迁移清单。

## 三层登记

| 层 | 配置 | 职责 |
|---|---|---|
| 菜单 | `config/app.yml` → `menu.menu_items[]` | 侧栏可见性、`group`、授权字段 |
| 迁移 | `config/migration_manifest.yml` | `done/mvp/stub/missing` + gaps |
| 能力包 | `config/feature_packs.yml` | SKU 出售单位 → 展开为 feature/menu_id |

用户覆盖菜单：`data/user/menu.yml`（开发）或 `%LOCALAPPDATA%/YCZH-TOA3/data/user/menu.yml`（安装包）。

## 新增模块标准路径

1. **Top3 + 三独到处** — `docs/research/<module_id>-top3.md`，主理人 `approved`
2. **业务页** — `modules/<id>/` 继承 `BasePage`
3. **登记** — `services/menu_registry.MIGRATED_MODULES`
4. **菜单** — `config/app.yml`（`show: false` 直到验收）
5. **清单** — `migration_manifest.yml`（有 gaps 不得 `done`）
6. **能力包** — 按需写入 `feature_packs.yml` 某 pack 的 `features`
7. **联调** — 主理人点验 → 清 gaps → `show: true`

## 发行版 / 体验版裁剪

- 配置：`config/app.release.yml` → `edition.id` + `edition.profile`
- 白名单：`config/editions/<profile>.yml` → `menu_whitelist`
- 过滤：`services/edition_profile.filter_menu_by_edition`（在 `access_control.filter_menu_items` 末尾）
- 环境变量覆盖：`TOA_EDITION=experience`

体验版 SKU：`feature_packs.experience_beta`（不可售，与 `editions/experience.yml` 对齐）。

## 授权与菜单关系

- `requires_license: false` 的办公模块默认全员可见（见 `access_control.ALWAYS_OPEN_IDS`）
- 需授权模块：license `features` 可写 menu_id 或 pack_id（经 `feature_packs.expand_features`）
- 菜单过滤顺序：**授权** → **发行版白名单**

## 更新检查

- 服务：`services/update_check.py`（短超时、工作线程，勿阻塞进页）
- 本地回退：`config/update_manifest.yml`
- 发布配置：`config/app.release.yml` → `update.*`
- UI：`AboutDialog` →「检查更新」

远程 manifest URL 留空时仅用本地清单；Portal 下载页为默认外链。

## 相关文档

- `docs/architecture/11-产品核心规范.md`
- `docs/功能清单与优先级.md`
- `.cursor/skills/toa3-add-feature/SKILL.md`
