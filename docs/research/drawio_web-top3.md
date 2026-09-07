# Draw.io Web · Top3 草案

> **status:** `research`（待主理人确认三独到处 → `approved`）  
> **module_id:** `drawio_web`  
> **范式：** [`docs/architecture/ARCH-05-引擎与Harness.md`](../architecture/ARCH-05-引擎与Harness.md)

## 1. 场景

谁：办公画流程图 / 架构图 / 组织图  
何时：在 TOA「引擎」内直接画，不必开浏览器上 diagrams.net  
输入：本机 `C:/AI/Draw.io`（jgraph/drawio 源码）  
输出：内嵌官方 Web；文件可本机保存

## 2. Top3（草案）

| # | 产品 | 学 | 不学 |
|---|------|----|------|
| 1 | diagrams.net 云端 | 功能全 | 强依赖外网 |
| 2 | draw.io Desktop | 本地文件 | 与办公套件割裂 |
| 3 | Visio / ProcessOn | 企业习惯 | 闭源/收费 |

## 3.5 独到之处（草案 · 待主理人勾选）

1. **与 OpenPencil / Comfy 同构 Host** — 探测 / 启停 / 内嵌。验收：引擎侧栏可见，点启动嵌入 `http://127.0.0.1:8080`。  
2. **钉死本机引擎目录** — 默认 `C:/AI/Draw.io`，Apache-2.0 自托管。验收：断网仍可打开编辑器壳。  
3. **不默认跳云端** — 静态托管 webapp，避免启动抢系统浏览器。验收：启动后只在套件内嵌。

- [ ] 主理人已确认上述 3 条
