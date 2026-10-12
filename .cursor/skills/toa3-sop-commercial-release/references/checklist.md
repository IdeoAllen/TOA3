# 商业发行验收 · 检查表（Agent 勾选）

## A. 摸底

- [ ] `APP_VERSION` = `update_manifest.version` = 线上 stable（或记清漂移）
- [ ] Wave★ 灯色：`screenshot_tool` / `clipboard_history` / `quick_notepad` / `quadrant_tasks` / `watermark_remover` / `directory_generator` / `screenshot_translate`
- [ ] `show:true` 且非 `done` 清单（发版风险）
- [ ] OPS-01：证书 / CDN / 设当前版 / 点验池状态

## B. A10.4 硬闸

- [ ] `python scripts/verify_all.py` → VERIFY ALL OK
- [ ] 无「`show:true` 且 gaps 含进页即崩/丢数据」
- [ ] `release_notes` 诚实（含已知限制）
- [ ] 授权/SKU：`tiyan` 可售 · `local_free` 非售 · 无 starter/experience_beta
- [ ] `release_config_guard` 绿（`commercial_smoke_checklist` 含）
- [ ] 商用冒烟：自动项绿 + 人工 1–5 主理人勾

## C. P0 整改落点

| 项 | 文件 / 命令 |
|----|-------------|
| 生产日志 | `config/app.release.yml` → `log_level: INFO` |
| 禁 DMS fallback | `allow_dms_fallback: false` · `dms_base_url: ""` |
| 侧栏收口 | `config/app.yml` `menu_items[].show` |
| 诚实说明 | `config/update_manifest.yml` `release_notes` |
| License 门禁 | `scripts/verify_license_gate.py` 已在 `verify_all.steps` |
| 冒烟自动 | `scripts/commercial_smoke_checklist.py` |
| 切版对齐 | `sync_release_version.py --from-live --require-match --commit` |

## D. P1 日用可售

- [ ] 主理人点验 Wave★ → 清 gaps → `done`（Agent 不代点）
- [ ] Wave F：点验或保持 `show:false`
- [ ] PROD-02 / `product.yml` 与灯色一致

## E. 对外话术

| 状态 | 可用话术 | 禁止话术 |
|------|----------|----------|
| A10.4 未过 | 内测包 / 预发 | 可商用当前版 |
| A10.4 过 · Wave★ mvp | 培训工具链可用；日用持续点验 | 办公八件套已完成；对标头部且更稳 |
| Wave★ done | 日用套件可售（仍写已知限制） | 隐瞒 Harness/激活需网限制 |
