# 05 · 控件库与 Qt Designer

## 1. 控件库的定位

**控件库 = 唯一对照与选用范围**（等同 TOA2 的「主题风格预览」页）。

- 路径：`modules/gallery/control_library_page.py`
- 启动：`python -m app.main`（当前默认打开控件库）
- 职责：展示所有标准控件 × 正常/禁用/选中等状态，**样式仅来自全局 QSS**

新增控件流程：

1. 在 `widgets/` 实现封装
2. 在控件库页增加实例
3. 更新 `docs/standards/控件库规范.md`
4. 业务模块方可引用

## 2. widgets 层规则

| 规则 | 说明 |
|------|------|
| 唯一入口 | 业务 `import widgets.xxx`，禁止裸 `QPushButton` 当主按钮 |
| 不设样式表 | 控件类内部禁止 `setStyleSheet` |
| class 对齐 QSS | 通过 `setProperty("class", ...)` 与 `gen_qss` 选择器一致 |
| 尺寸用 metrics | `widgets/metrics.py`，禁止魔法数字散落 |

规划中的控件文件：

```
widgets/
  buttons.py      PrimaryButton, SecondaryButton, DangerButton, RowButton
  inputs.py       LineEdit, ComboBox, SpinBox, PathRow
  labels.py       TitleLabel, SectionLabel, SemanticLabel
  tables.py       StandardTable
  lists.py        ListPanel（对标 BaseListPanel）
  dialogs.py      EditDialog 基类
```

## 3. Qt Designer 工作流

### 3.1 安装与启动

```powershell
pip install PySide6
pyside6-designer
```

### 3.2 文件位置

- 壳：`ui/shell/*.ui`
- 模块：`ui/modules/<feature>/page.ui`
- 说明见 `ui/README.md`

### 3.3 编辑步骤

1. Designer 拖控件，设 **objectName**（英文，稳定）
2. 布局用 Layout，**禁止**固定 geometry（除极小图标）
3. 需要标准外观的控件 → **提升为自定义类**（Promoted widgets）指向 `widgets.*`
4. 保存 `.ui`，**不写** `styleSheet` 属性（全局 QSS 负责）

### 3.4 加载 .ui

```python
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile

loader = QUiLoader()
file = QFile("ui/modules/foo/page.ui")
file.open(QFile.ReadOnly)
widget = loader.load(file, parent)
file.close()
```

或使用 `pyside6-uic` 生成 `ui_foo_page.py` 后继承（团队选定一种，统一全项目）。

### 3.5 Designer 与主题

Designer 内看到的是 **原生 Qt 样式**，不是商务蓝。

**验收方式**：

1. 运行控件库或模块页
2. 截图对比
3. `scripts/verify_gallery.py`（规划）自动检查尺寸/色

## 4. 控件库当前内容（POC）

| 分区 | 控件 |
|------|------|
| 标签与语义色 | 四级字号 + success/warning/danger/info |
| 按钮 | 主/次/危险/行内 + 禁用 |
| 输入 | LineEdit、ComboBox、SpinBox |
| 勾选单选 | CheckBox、RadioButton |
| 进度 | ProgressBar |
| 页签 | TabWidget |
| 表格 | TableWidget + 表头 + 选中行 |

## 5. 禁止事项（与 TOA2 铁律对应）

- 在 `modules/**` 新建另一套按钮封装绕过 `widgets`
- 为好看在单页 `setStyleSheet`
- 在 Designer 里写死颜色
- Notebook 当模块外壳

## 6. 下一章

[06-业务模块规范](06-业务模块规范.md)
