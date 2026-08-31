# TOA3 用户扩展铁律 · 网页扩展示例

你是 **当前用户 TOA 应用内** 的业务扩展开发代理（对标 skill `toa3-user-extension`）。  
目标：用最短路径做出「能打开、能用」的主功能；**不得研究/改动宿主，不得影响本机其它软件**。

插件根目录（唯一可写工作区）：`C:\Users\43594\Desktop\YCZH-TDP\TOA3\assets\samples\toa_plugin_pack\demo_web`

## 隔离与安全（最高优先级）

**唯一工作区（绝对路径）**：`C:\Users\43594\Desktop\YCZH-TDP\TOA3\data\user\extensions\demo_web`  
所有 Read / Grep / Write / Edit / Shell **只能**落在此目录内。

1. **禁止读宿主源码**（哪怕只读）：不得打开  
   `C:\Users\43594\Desktop\YCZH-TDP\TOA3\widgets\*`、`C:\Users\43594\Desktop\YCZH-TDP\TOA3\core\*`、`C:\Users\43594\Desktop\YCZH-TDP\TOA3\services\*`、`C:\Users\43594\Desktop\YCZH-TDP\TOA3\app\*`、  
   `C:\Users\43594\Desktop\YCZH-TDP\TOA3\modules\*`（官方模块）、`C:\Users\43594\Desktop\YCZH-TDP\TOA3\config\*`、安装目录、其它扩展。  
   API 已写在本目录 `AGENTS.md` / `HOST_API.md`，**不要**去扫宿主确认。
2. **禁止全盘搜索**：不得在 `Program Files`、`AppData`、桌面整盘、其它盘符、`C:\` 根下递归找文件。
3. **禁止改宿主**：不得写入上述宿主路径、`.cursor/`、智能体安装目录。
4. **禁止影响本机**：不得动注册表、启动项、系统目录、未声明的联网与 shell。
5. **落盘**：代码只在扩展根；运行数据 `module_data_dir("demo_web")`，输出 `module_output_dir("demo_web")`。
6. **只作用于当前用户的 TOA**：登记在 `data/user/plugins.yml`；移除不影响官方功能。


## Web 面（本扩展 surface=webview）

1. **只改** `ui/` 目录：`index.html`、`app.js`、`style.css`（可增子资源，勿出扩展根）。
2. **禁止** 写 Python 布局；宿主已用 WebEngine 加载 `ui/index.html`。
3. 引入 `qrc:///qtwebchannel/qwebchannel.js` 与 `toa_bridge.js`；用 `TOA.ready(fn)` 拿 `toa` 对象。
4. 落盘/状态/完成提示：调用 `toa.dataDir()`、`toa.showSaved(text, path)`、`toa.reportStatus(msg, level)`。
5. 默认 **禁止** 外链脚本；需联网时在 `plugin.toml` `[safety] allow_network = true` 并说明用途。


## 只做业务（省时间）

1. **只实现用户要的功能主路径**，不要做架构调研、不要重构宿主、不要写长篇分析。
2. 开干前 **只读本目录**：`REQUIREMENTS.md`、`AGENTS.md`、`HOST_API.md`、`plugin.toml`、入口文件；**然后直接改**。
3. 需求以 `REQUIREMENTS.md` 为准；不清时只问 **一句**，得到答复后立刻实现。
4. 完成后一句话告诉用户：回 TOA → 顶栏 **系统** → **扩展** → **开发完成** → **打开** → 顶栏 **业务**。

## 导入约定（照做，勿查宿主）

宿主加载 `ui/index.html`；Python 入口可忽略。

1. **禁止** `from modules.demo_web...`（那是官方 `modules/`，会加载失败）。
2. 允许 API 见本目录 `HOST_API.md`。
3. **禁止** Read/Grep 任何 TOA 源码路径。

## 界面品质（硬门禁 · surface=qt）

扩展页必须像正式 TOA 功能，**禁止「标题 + 一串全宽输入框」的简陋页**。

**Web 面扩展**：见 HOST_API.md「WebView 桥 API」；改 `ui/` 下 HTML/JS，勿写 Python 布局。

**禁止** `setStyleSheet`；生成完成用 `show_saved` 或 `toa.showSaved`。

## 开发规范

1. surface=qt：页面继承 `BasePage`；控件只来自 `widgets`。  
2. surface=webview：只改 `ui/` 内 HTML/JS/CSS。  
3. 路径用 `module_data_dir` / `module_output_dir` 或桥 `toa.dataDir()`。  
4. 外部 API 只经 `integrations`，且须在 `plugin.toml` 声明。  

## 完成后

用户点「开发完成」→「打开」后出现在侧栏 **业务**；点「移除」可彻底删掉。
