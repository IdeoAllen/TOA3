# dshm — DeepSeek Harness 管理终端

借鉴 [Codex CLI](https://github.com/openai/codex) 与 [Claude Code](https://claude.com/claude-code) 的优点，给
DeepSeek Harness（DSH）做的一个零依赖命令行管理终端。

- 像 **Codex `resume`**：列出历史会话、按编号 / id 前缀恢复、跨会话 `dsh-session:` 引用。
- 像 **Claude Code `/status`、`/usage`、`/cost`**：一眼看清工作区、会话、目标、token 用量与上下文压力。
- 纯 Node 内置模块，**无需 npm install**，读的是 Harness 已经落盘的只读数据（`$DSH_HOME`）。

## 数据来源（只读，除 archive）

`dshm` 读取 Harness 的主目录数据，与 Web GUI 共享同一份状态：

| 文件 | 用途 |
|---|---|
| `storages/workspace.json` | 工作区注册表、会话分组、归档集合 |
| `storages/session_projcache.json` | 会话投影缓存：标题、统计、token、上下文、权限、目标、待办 |
| `settings.yaml` | 默认模型等设置（最小 YAML 子集解析） |

> 只有 `archive` / `unarchive` 会写 `workspace.json`（原子替换，保留其余字段）。为避免与正在运行的
> Web GUI 竞争写入，建议在 GUI 空闲时归档。

## 运行

```sh
# 方式一：直接运行（Windows）
dshm\dshm.cmd status

# 方式二：node 直接运行
node dshm/bin/dshm.js status

# 方式三：全局安装
cd dshm && npm link
dshm status
```

不带命令时进入交互式终端：

```sh
node dshm/bin/dshm.js
```

## 命令

| 命令 | 说明 | 借鉴 |
|---|---|---|
| `status` | 仪表盘：工作区 / 会话 / 目标 / 用量概览 | Claude `/status` |
| `top` | 实时刷新状态面板（Ctrl+C 退出） | — |
| `web` / `ui` | 启动本地网页管理界面（默认 `http://127.0.0.1:8787`） | — |
| `ls` / `sessions` | 列出全部会话（`--all` 含归档） | Codex `resume` 列表 |
| `show <id>` | 会话完整元数据（统计 / token / 上下文 / 权限 / 目标 / 待办） | Claude `/usage` |
| `usage` | 全局 + 按会话的 token / 上下文用量 | Claude `/cost` |
| `workspaces` | 列出工作区 | — |
| `goal` | 显示当前活跃目标 | — |
| `resume [id]` | 恢复会话；无 id 时列出候选 | Codex `resume` |
| `archive <id...>` / `unarchive <id...>` | 归档 / 取消归档（可多个 id 批量） | — |
| `export [id...]` | 导出可读 Markdown/JSON 会话记录（`--all` 全部） | **GUI 缺** |
| `backup` | 无损备份：复制原始会话日志 + 元数据 | **GUI 缺** |
| `search <词>` | 跨工作区/会话全文搜索（`--reasoning` 含推理） | **GUI 缺** |
| `trend <id>` | 每步 token 用量趋势图 | **GUI 缺** |

## 选项

```text
--home <path>   指定 DSH 主目录（默认 $DSH_HOME 或 ~/.dsh）
--json          以 JSON 输出（status/ls/show/usage/workspaces/goal）
--all           列出会话时包含已归档
--open          resume/web 时尝试在浏览器打开界面
--host <addr>   web 绑定地址（默认 127.0.0.1）
--port <端口>   web 监听端口（默认 8787）
--watch <秒>    top 刷新间隔（默认 2 秒）
--no-color      禁用颜色（管道输出时默认禁用）
```

## 本地网页界面

```sh
dshm web                 # 启动，浏览器打开 http://127.0.0.1:8787
dshm web --open          # 启动并自动打开浏览器
dshm web --port 9000     # 换端口
```

页面提供：概览卡片、目标条、会话表格（搜索 / 过滤归档 / 点击查看详情）、详情抽屉里的
归档 / 取消归档、复制 `dsh-session:` 引用 URI、打开 Web GUI、**每步 token 用量趋势图**、
**导出 Markdown/JSON**，顶栏**全文搜索**，以及 3 秒自动刷新。

## 对比 Harness Web GUI 新增的能力

这些是 GUI 里没有、`dshm` 补上的：

| 能力 | 命令 | 网页版 |
|---|---|---|
| 跨工作区/会话全文搜索 | `search <词>` | 顶栏搜索框 |
| 每步 token 用量趋势 | `trend <id>` | 详情抽屉图表 |
| 可读会话导出（Markdown/JSON） | `export` | 详情抽屉按钮 |
| 无损原始备份 | `backup` | — |
| 批量归档/取消归档 | `archive <id...>` | 表格+抽屉 |

> 数据来源：会话日志为 `session.jsonl.zstd`（zstd 帧拼接），`dshm` 按帧切分后用
> Node 内置 `zlib.zstdDecompressSync` 解压，读取 `user/message` 与 `assistant/message`
> （含每步 token 用量）事件。

## 恢复会话说明

Harness 的 `web` / `headless` profile 目前没有 `--resume` 命令行标志（恢复在 Web GUI 侧边栏完成）。
因此 `dshm resume <id>` 输出：

1. 该会话的 `dsh-session:<base64url(json(id))>` 引用 URI（可用于跨会话 `@mention`）；
2. Web GUI 地址，`--open` 时直接打开浏览器。

## 目录结构

```text
dshm/
├─ bin/dshm.js     入口与参数解析
├─ lib/home.js     DSH 主目录解析
├─ lib/format.js   ANSI 颜色 + CJK 宽度感知排版
├─ lib/store.js    读取 workspace / session 缓存 / settings 并归一化
├─ lib/commands.js 各命令实现与分发
├─ lib/repl.js     交互终端 + top 实时面板
├─ lib/server.js   本地网页界面服务（Node 内置 http）
├─ lib/web/index.html  网页仪表盘（单文件，无构建）
├─ dshm.cmd        Windows 启动脚本
└─ package.json
```
