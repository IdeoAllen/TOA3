# 授权状态验收夹具

用于主理人切换不同 **基础版 / 授权版 / 正式版** 档位，点验顶栏 Chip、购买页、模块门禁。

## 快速切换

```powershell
# 列出 8 种场景
python scripts/apply_license_fixture.py --list

# 应用某一档（会自动备份当前 config/license.json）
python scripts/apply_license_fixture.py --apply 01_trial_standalone_active

# 重启应用
python -m app.main

# 验收完恢复现场
python scripts/apply_license_fixture.py --restore
```

查看当前运行时档位（不切换）：

```powershell
python scripts/apply_license_fixture.py --status
```

导出静态 JSON（可选）：

```powershell
python scripts/apply_license_fixture.py --export-all
```

## 八档场景

| ID | 场景 | 预期顶栏 Chip | 重点验收 |
|----|------|---------------|----------|
| `01_trial_standalone_active` | 基础版 · 单机体验中 | 基础版 | 基础模块可用；付费模块引导升级 |
| `02_trial_standalone_expired` | 基础版 · 单机体验已到期 | 续费 | 基础模块仍可用；付费模块拦截 |
| `03_unlicensed_fresh` | 基础版 · 未激活 | 基础版 | 登录窗点「进入软件」或授权码登录 |
| `04_auth_trial_active` | 授权版 · 体验码有效 | 授权版 | 账号区显示体验授权 + 有效期 |
| `05_auth_trial_expired` | 授权版 · 体验已到期 | 续费 | 购买页/模块拦截文案 |
| `06_auth_admin` | 授权版 · 管理员 | 授权版 | 全部模块可开；运营台同步可用 |
| `07_official_paid_active` | 正式版 · 套餐有效 | 正式版 | 付费模块全开；Chip 为正式版 |
| `08_official_paid_expired` | 正式版 · 套餐已到期 | 续费 | 基础模块可用；付费模块续费引导 |

## 建议点验路径

1. **顶栏 Chip** — 文案与颜色（试用=蓝、授权/正式=绿、到期=黄）
2. **账号菜单** — 档位 · 套餐 · 有效期摘要
3. **系统 → 授权** — 与 Chip 一致，无「免费版」字样
4. **订阅购买** — 加载套餐、手机号可编辑，无 eternal「加载中…」
5. **模块门禁** — 各档下各试 1 个 `requires_license:true` 与 `false` 模块

## 注意

- 夹具为 **本机离线验收** 设计：联网授权场景带 `online_status=active` 与近期 `last_online_ok_at`，离线宽限内可登录；**不依赖真实 TOA 云服务码**。
- 应用前会自动备份至 `config/license.json.bak.acceptance`。
- 开发环境请确认 `config/app.dev.yml` 中 `license.dev_grant_all: false`，否则档位判断会被开发全开通覆盖。
