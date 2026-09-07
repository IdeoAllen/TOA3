# ComfyUI Web · Top3 草案

> **status:** `research`（待主理人确认三独到处 → `approved`）  
> **module_id:** `comfyui_web`  
> **范式：** [`docs/architecture/ARCH-05-引擎与Harness.md`](../architecture/ARCH-05-引擎与Harness.md)

## 1. 场景

谁：已用 Comfy Desktop「大成哥-2」工作流的运营 / 制作  
何时：在 TOA「引擎」里直接开原版 ComfyUI，不必另开桌面端  
输入：本机 `D:/Comfy-Desktop/ComfyUI-Installs/大成哥-2`（端口 **8189**）  
输出：内嵌官方 Web；可浏览器打开同一 URL；与「媒体工坊」API 出图并存

## 2. Top3（草案）

| # | 产品 | 学 | 不学 |
|---|------|----|------|
| 1 | ComfyUI Desktop | 原版节点图、插件生态 | 与办公套件割裂、多开端口难记 |
| 2 | 独立浏览器开 8189 | 零改造 | 无启停、无壳内发现 |
| 3 | 仅媒体工坊 API | 一键出图 | 不能跑完整节点/自定义工作流 |

## 3.5 独到之处（草案 · 待主理人勾选）

1. **与 OpenPencil / Harness 同构 Host** — 探测 / 启停 / 内嵌一套范式。验收：顶栏引擎可见，点启动后嵌入 `http://127.0.0.1:8189`。  
2. **钉死大成哥-2 · 8189 示例** — 默认根与端口对齐本机常用实例，且 `--disable-auto-launch` 不抢外部浏览器。验收：启动不弹系统浏览器，套件内可见画布。  
3. **与媒体工坊分工清楚** — API 快出图 vs 原版后台深工作流，互不替代。验收：侧栏同时有「ComfyUI（大成哥-2）」与「媒体工坊」。

- [ ] 主理人已确认上述 3 条
