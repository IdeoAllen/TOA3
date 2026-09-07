# OpenPencil · Top3 草案

> **status:** `research`（待主理人确认三独到处 → `approved`）  
> **module_id:** `open_pencil`  
> **范式：** [`docs/architecture/ARCH-05-引擎与Harness.md`](../architecture/ARCH-05-引擎与Harness.md)

## 1. 场景

谁：需要本地设计编辑（.fig / .pen）的运营 / 行政  
何时：在 TOA「引擎」里直接画，不必另开终端  
输入：本机已 clone 的 OpenPencil 仓库  
输出：内嵌官方 Web；可浏览器打开同一 URL

## 2. Top3（草案）

| # | 产品 | 学 | 不学 |
|---|------|----|------|
| 1 | Figma Desktop | 画布成熟 | 闭源、强云依赖 |
| 2 | Penpot | 开源协作 | 偏账号型浏览器 |
| 3 | OpenPencil 独立窗 | 本地 AI 设计 | 与办公套件割裂 |

## 3.5 独到之处（草案 · 待主理人勾选）

1. **Harness 同构启停** — 检测安装 / 一键启动 / 内嵌，不开终端。验收：点启动后健康条变「就绪」并出现画布。  
2. **挂进办公套件引擎栏** — 与截图/剪贴板同壳，后续可接力。验收：顶栏「引擎」可见 OpenPencil。  
3. **根目录可手选** — 多 clone 共存。验收：「指定目录」后状态指向新根。

- [ ] 主理人已确认上述 3 条
