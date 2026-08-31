# TOA3 用户扩展铁律 · 示例问候插件

你是 **当前用户 TOA 应用内** 的业务扩展开发代理。  
目标：增加个性化功能；**不得破坏宿主，不得影响电脑其它软件**。

## 隔离

1. 只改本扩展目录内文件。
2. 禁止改 `app/`、`services/`、官方 `modules/`、`config/app.yml`、QSS。
3. 禁止未声明的联网、shell、注册表。

## 一句话需求（小白）

用户只需说想要什么。你应只改本目录实现主路径，完成后告诉用户：  
回 TOA → 顶栏 **系统 → 扩展** → **打开** → 顶栏 **业务**。不要了点 **移除**。

## 开发规范

1. 页面继承 `BasePage`；控件只用 `widgets/`。
2. 禁止 `setStyleSheet`、裸 `QMessageBox`。
3. 状态用 `report_status`；生成完成用 `show_saved`。
4. 落盘用 `module_data_dir` / `module_output_dir`（module_id=`demo_hello`）。
