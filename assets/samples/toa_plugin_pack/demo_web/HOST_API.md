# 宿主 API 速查（只读本文件，禁止去扫 TOA 源码）

本文件已复制进扩展沙箱。需要 API 时 **只读这里**，不要 Read/Grep  
`TOA3/widgets`、`TOA3/core`、`TOA3/services`。

## 常用 import（surface=qt）

```python
from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_info, show_warning, show_error, ask_confirm
from services.storage_paths import module_data_dir, module_output_dir
from services.os_open import open_in_file_manager
from widgets import (
    ScrollPage, PageHeader, FormSection, HintLabel, SemanticLabel,
    LineEdit, PlainTextEdit, ReadOnlyPlainTextEdit, DateEdit, ComboBox,
    CheckBox, Switch, PrimaryButton, SecondaryButton, DataTable,
)
```

## 控件清单（`from widgets import …`）

PageTitle, SectionTitle, HintLabel, SemanticLabel,  
PrimaryButton, SecondaryButton, DangerButton, MessageKindButton, InlineButton,  
LineEdit, PasswordLineEdit, PlainTextEdit, ReadOnlyPlainTextEdit, TextEdit, ReadOnlyTextEdit,  
ComboBox, SpinBox, DateEdit, CalendarWidget, CheckBox, Switch, RadioButton, Slider,  
FormSection, ScrollPage, PageHeader, HBox, VBox, FormRow, PathRow, GridBox, SplitPane,  
ListWidget, TreeWidget, ProgressBar, TabWidget, DataTable, DialogButtonRow,  
ListPanel, ManageTablePanel, FormEditDialog,  
ToolLaunchCard, StatusDot, ThemePicker

## 关键函数签名（照抄即可）

```python
show_saved(self, "已保存", path)
data_dir = module_data_dir("demo_web", create=True)
out_dir = module_output_dir("demo_web", create=True)
self.report_status("说明文字", level=StatusLevel.SUCCESS)
```

## 入口

宿主 WebEngine 加载：`ui/index.html`（见 plugin.toml entry.web_root）。
  
禁止 `from modules.demo_web...`（那是官方 modules 命名空间）。


## WebView 桥 API（surface=webview · JS 侧）

页面须引入：

```html
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="toa_bridge.js"></script>
```

```javascript
TOA.ready(function (toa) {
  toa.reportStatus('就绪', 'success');
  toa.showSaved('已保存', toa.outputDir());
  var pal = TOA.parsePalette(toa.themePalette());
});
```

| 方法 | 说明 |
|------|------|
| `toa.pluginId()` | 扩展 id |
| `toa.pluginName()` | 显示名 |
| `toa.dataDir()` | 数据目录绝对路径 |
| `toa.outputDir()` | 输出目录绝对路径 |
| `toa.reportStatus(text, level)` | level: info/success/warning/error |
| `toa.showSaved(text, path)` | 绿色完成 + 打开所在目录 |
| `toa.readTextFile(relative)` | 读 data 目录内相对路径 |
| `toa.writeTextFile(relative, content)` | 写 data 目录内相对路径 |
| `toa.themePalette()` | 主题 JSON 字符串 |
| `toa.themeId()` | 当前主题 id |

资源只放 `ui/`；导航默认限制在扩展目录内；联网须 `allow_network = true`。

