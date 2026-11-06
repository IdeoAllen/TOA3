# TOA3 开发约定（入口）

本仓库的开发、打包、发版规范以 `docs/规范/` 为准：

- `STD-01` 工程标准，`SOP-04-打包发版.md`，`SOP-08-商业发行验收.md`
- 进度与交接唯一文件：`docs/handoff/OPS-01-交接与进度.md`
- 版本唯一来源：`app/version.py`

## 与巨龙数变场的协作（2026-11-06 起）

TOA3 已纳入巨龙数变场体系（巨龙 = 身份中心与内容/资产阵地，TOA3 = 终端生产工具）。

- 三端协议（TOA 注册码、巨龙密钥与 MCP、推送接口、扩展包与资产映射）只在巨龙仓库维护：
  `../julong-platform/docs/protocol/`。本仓库引用，不复制。
- 改动涉及巨龙接口时：先改协议文档并升版本 → 巨龙实现 → TOA3 实现，发版记录里互相注明对方版本。
- 对巨龙的调用集中放在 `services/julong_client.py`；Harness 侧 MCP 连接集中放在 `services/harness_mcp.py`。
- 巨龙相关能力一律是可选联网功能，`local_free` 与离线模式不得受影响。
- 密钥（共享密钥、巨龙密钥）只存 credentials / 服务器 `.env`，不写入仓库与明文配置。
