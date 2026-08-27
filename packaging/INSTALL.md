# TOA3 · Windows 产品安装说明

## 用户侧

| 动作 | 做法 |
|---|---|
| **安装** | 双击 `TOA3-Setup-vX.Y.Z.exe` |
| **激活** | 装好后启动软件 → 向管理员索取 `TOA2-...` 授权码 → 点击「激活授权」联网激活 |
| **换码 / 到期 / 停用** | **无需卸载**；申请新码后重新激活即可 |
| **升级** | 再装新版本 setup（同一 AppId 自动覆盖） |
| **卸载** | Windows「设置 → 应用」或开始菜单 `Uninstall TOA3` |

要点：

- **默认不要求管理员**；可选在向导里提升后装到 Program Files
- **安装时不要求授权码**
- 安装目录为 ASCII：`%LOCALAPPDATA%\Programs\TOA3`（与 TOA2 `%LOCALAPPDATA%\Programs\TOA` 可并存）
- 用户数据目录：`%LOCALAPPDATA%\YCZH-TOA3`

可选：静默安装并顺便激活：

```bat
set TOA_LICENSE=TOA2-你的授权码
TOA3-Setup-vX.Y.Z.exe /VERYSILENT /NORESTART /LICENSE=%TOA_LICENSE%
```

## 构建（对齐 TOA2）

```bat
winget install JRSoftware.InnoSetup
python packaging\build_windows.py --clean --msi
```

正式分发文件：`packaging\dist\TOA3-Setup-vX.Y.Z.exe`

升级脚本（可选）：`packaging\dist\TOA3-upgrade.bat`

## 发版（DMS）

TOA3 桌面安装包与 DMS 后端发版分离。在 DMS 管理端更新下载链接/版本说明时：

1. 只建 **draft** 发布单
2. 主理人审核通过后，再执行 `DMS\deploy\deploy.ps1`

详见 `.cursor/rules/dms-release-deploy.mdc`
