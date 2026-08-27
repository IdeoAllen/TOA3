# Qt Designer 文件目录

- 所有 `.ui` 放于此目录（按模块分子目录）
- 用 **pyside6-designer** 打开编辑
- 保存后由业务 `page.py` 加载，不在 Designer 里写业务逻辑

示例（后续添加）：

```
ui/shell/main_window.ui
ui/gallery/control_library.ui
```

控件库当前用纯 Python 搭建（`modules/gallery/control_library_page.py`），验证 QSS 后再拆为 `.ui`。
