# 24 · 壳层与设置 IA · Figma 规划 Brief（设计师）

> **状态**：工程已按 Target 态落地 · 2026-08-28  
> **承接**：工程侧 IA 已按 [23-运营台与终端设置职能边界.md](../architecture/23-运营台与终端设置职能边界.md) 收敛；**高保真与交互细节交设计师在 Figma 定稿**。  
> **已有文件**：在 Phase 1 交付物上 **增量**，不另起炉灶。

| 资产 | 链接 |
|------|------|
| FigJam 产品规划 | https://www.figma.com/board/ITYN3rMxRYTYmt1cBl3b3b |
| Figma 高保真 Platform UX | https://www.figma.com/design/DuBuOok3nyJMSfVmarqxIW |

---

## 1. 设计目标（一句话）

把「权限不够就买、版本旧就升、登录了就查看/退出、管理员维护、用户只查看」做成**顶栏 + 系统设置**两层 IA，**不与运营台重复**，且与代码真相源一致。

---

## 2. 用户心智 · 五句口诀（评审锚点）

| 口诀 | 设计表现 |
|------|----------|
| 权限不够就买 | 顶栏 **授权 Chip** + 账号弹窗「一键开通」→ 支付/激活流 |
| 版本不新就升 | **应用** Tab / 关于弹窗「检查更新」；有新版本非阻塞提示 |
| 登录了就查看 | **账号**（人像）= 只读摘要 + 退出 |
| 管理员就维护 | **本机管理** 子页：品牌 / 授权 / 菜单 / 接入 / 诊断 |
| 用户就查看 | **偏好** + **应用**；无名单编辑、无 SKU 表 |

---

## 3. 信息架构（目标态 · 须在 Figma 画清）

### 3.1 顶栏

```
[Logo] [品牌名] [授权Chip] ··· [主题] [全屏] [Ctrl+K] [齿轮设置] [切换身份*] [人像账号]
* 本机 ≥2 个已发卡用户时显示 · Alt+U
```

| 控件 | 打开什么 | 禁止出现 |
|------|----------|----------|
| 授权 Chip | 未授权→购买；已授权→摘要/续费 | SKU 编辑表 |
| 齿轮 Alt+S | 系统设置页 | 退出登录 |
| 切换身份 | 本机用户列表 → 切换 | 运营台订单 |
| 人像 | 账号弹窗：查看 / 切换 / 开通 / 退出 | 品牌/菜单维护表单 |
| ~~顶栏 ℹ 关于~~ | **已移除** → 关于走热键 Alt+Shift+O 或 应用 Tab | 与设置重复 |

### 3.2 系统设置 · 顶层 Tab（最多 4 个）

| Tab | 谁 | 内容 |
|-----|-----|------|
| **偏好** | 全体 | 主题、快捷键；普通用户含「模型与 AI」 |
| **本机管理** | 仅管理员 | 二级：品牌 · 授权 · 菜单 · 能力接入 · 诊断 |
| **开通与续费** | 未授权时 | 一键开通 + 粘贴授权码（与 Chip 同链路） |
| **应用** | 全体 | 版本、检查更新、关于产品…、重启、完全退出 |

**对比旧稿（需 Before/After）**：原 9 个平铺 Tab（外观、品牌、授权、菜单…、应用与更新、关于产品）→ 上表 3–4 Tab。

### 3.3 运营台边界（FigJam 一页即可）

终端 **不画**：功能包 SKU 编辑、订单台、发版表单。  
终端 **只读/跳转**：云服务地址、machine_id、购买外链。

---

## 4. Figma 增量帧清单（建议新增 Section）

在 **Figma · Platform UX v1** 中新增页面 **`Desktop · Shell IA v2`**：

| 帧 | 名称 | 内容 | 标注 |
|----|------|------|------|
| S1 | 顶栏 · 管理员 · 已授权 | 全控件 + Chip 绿 | Target |
| S2 | 顶栏 · 普通用户 · 已授权 | 无「本机管理」入口暗示 | Target |
| S3 | 顶栏 · 未授权 | Chip 红/橙 + 开通 CTA | Target |
| S4 | 切换身份对话框 | 用户表 + 当前行高亮 + 切换/取消 | Target · `SwitchUserDialog` |
| S5 | 账号弹窗 · 已授权 | 摘要 + 切换/设置/关于/退出 | Target |
| S6 | 账号弹窗 · 未授权 | 一键开通主按钮 | Target |
| S7 | 设置 · 偏好 | 主题 + 快捷键 (+ 用户侧模型) | Target |
| S8 | 设置 · 本机管理 · 授权 | 嵌套 Tab，含授权用户 + 云服务连接 | Target |
| S9 | 设置 · 应用 | 版本 + 检查更新 + 关于… + 重启/退出 | Target |
| S10 | 设置 · 开通与续费 | 未授权态 | Target |
| S11 | Before · 9 Tab 平铺 | 截图还原用户反馈的「重复感」 | Current |
| S12 | IA 对照 sticky | 顶栏/设置/运营台 三列职责表 | Spec |

**FigJam 增量**（board 同链接）：新增 Section **「Shell IA v2 · 用户路径」**，含：

- 角色 × 入口矩阵（管理员 / 用户 / 未授权）
- 三条短路径原型：买 → 用 → 换身份 → 升版本 → 退出
- 与 L/M 系列帧的交叉引用（License 桌面帧不必重画，只改标注）

---

## 5. 原型路径（Prototype 5 条 · 与旧 Flow 并列）

1. **多用户切换**：S4 选关佳伟 → 侧栏菜单变窄 → 状态栏用户名更新  
2. **管理员维护**：S8 授权子页发卡 → 不回运营台  
3. **用户只看**：S5 账号弹窗 → S7 偏好 → 无本机管理 Tab  
4. **未授权购买**：S3 Chip → S10 开通 → 回到 S1  
5. **升版本**：S9 检查更新 → 非阻塞 toast → 下载页外链  

---

## 6. 设计约束（硬）

- Token：`config/themes/toa_complete.json` · 布局 `config/ui_spec.yml` · 控件 `widgets/`  
- 禁止硬编码色；SemanticLabel 四态（success/warning/danger/info）  
- 进页/弹窗 **禁止** 同步 30s 联网（检查更新、联网校验均异步）  
- 中文办公字体栈（Microsoft YaHei UI 系），与现 Platform UX Foundations 一致  
- Release 画面不出现 `DMS` / `TOA2-` / `skip_login` 等开发键名（见 doc 21 §5.1）

---

## 7. 工程对照（设计师改稿时对齐）

| UI | 代码路径（实现中/已合并分支） |
|----|-------------------------------|
| 顶栏 | `app/shell.py` |
| 切换身份 | `app/switch_user_dialog.py` |
| 账号 | `app/user_profile_dialog.py` |
| 关于 | `app/about_dialog.py` |
| 设置页 | `modules/system_settings/settings_page.py` |
| 本机管理 | `modules/system_settings/local_admin_section.py` |
| 应用 Tab | `modules/system_settings/app_update_section.py` |
| 职能边界 | `docs/architecture/23-*.md` |

**说明**：部分 IA 代码在 `cursor/v311-upgrade-commerce-platform` 之上仍有工作区改动，Figma 以 **Target 态** 为准；Current 用 S11 + 用户截图。

---

## 8. 交付与评审

| 步骤 | 产出 | 负责人 |
|------|------|--------|
| 1 | FigJam Shell IA v2 Section + 路径图 | 设计师 |
| 2 | Figma S1–S12 + Before/After | 设计师 |
| 3 | 5 条 Prototype + Spec sticky | 设计师 |
| 4 | 主理人过稿（五句口诀 + 运营台不重复） | 产品 |
| 5 | 开发按帧改 QSS/布局（不再扩 Tab） | 工程 |

**预估**：1–1.5 工作日（含一轮反馈）。

---

## 9. 不在本次范围

- Wave★ 八件套业务页重画  
- Harness 内嵌 Web  
- 运营台 Admin 重设计（C1–C8 已有，仅补交叉引用）  
- 桌面安装向导 U 系列（除非「应用·检查更新」联动需改 U3）

---

返回 [架构索引](../architecture/README.md) · 关联 [21-平台体验…](../architecture/21-平台体验托盘升级授权与发行迭代规划.md)
