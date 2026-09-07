# TOA3 脚本 ↔ 场景映射

| 场景族 | 脚本 | 断言要点 |
|--------|------|----------|
| 壳层铁律 | `scripts/verify_shell_hardening.py` | Loading、系统域、Comfy 隐藏、handoff、beforeunload API |
| 引擎↔业务 | `scripts/debug_engines_to_business.py` | SESSION OK、`painted_url` 端口、beforeunload 陷阱 |
| 引擎压测 | `scripts/stress_engines_business.py` | 狂切不崩、共享 owner |
| 全菜单 | `scripts/stress_all_menus.py` | 可见菜单可进 |
| 总门禁 | `scripts/verify_all.py` | 上列+MVP+gallery+audit |
| 闪退排错 | skill `toa3-sop-debug-crash` | faulthandler + DEBUG 会话 |
| 迁移审计 | `scripts/audit_migration.py` | gaps/status 一致 |
| 架构超边 | `scripts/audit_architecture.py` | 分层/超边 |

## 模块级（按需）

| 模块 | 建议 |
|------|------|
| 控件库 | `verify_gallery.py` |
| 本地 Web 引擎 | `verify_local_web_engines.py`（若存在） |
| 无脚本模块 | 在 debug/stress 路径加 navigate；或新增 `scripts/verify_<id>.py` 最小冒烟 |

## 双开注意

正式版 `TOA3.exe` 与开发版并存会抢 WebEngine 缓存；诊断/压力测优先关掉正式版。
