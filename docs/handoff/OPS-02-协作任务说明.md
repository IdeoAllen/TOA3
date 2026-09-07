# TOA3 · 人机协作任务说明

> 本文写全「怎么用协作表」，可独立阅读。  
> **任务进度正文**在同目录 `OPS-01-交接与进度.md`；**机读列表**在 `collab_tasks.json`。

---

## 1. 开发版 vs 正式版（数据不共用）

| 你打开的是 | 特征 | 四象限任务文件 |
|------------|------|----------------|
| 正式版（安装包） | 首页绿「正式版」 | `%LOCALAPPDATA%\YCZH-TOA3\data\module\quadrant_tasks\tasks.json` |
| 开发版（仓库跑） | DEV / 无绿标 | 仓库 `data\module\quadrant_tasks\tasks.json` |

截图若是绿标正式版，必须 seed 到 **release**，只写开发目录会看不见。

---

## 2. 导入到四象限

```powershell
cd C:\Users\43594\Desktop\YCZH-TDP\TOA3
python scripts/seed_collab_tasks.py --edition both --wipe-collab
```

然后：顶栏 **办公** → **四象限任务**（若已打开，先切走再回来刷新）。

备选：把 `collab_tasks.json` 复制为对应 edition 的 `tasks.json`（会整表覆盖，慎用）。

---

## 3. 在记事本中打开本说明

TOA → **办公** → **快速记事** → **更多** → **打开协作任务表**  
会加载本 Markdown；任务勾选状态以四象限 / `OPS-01-交接与进度.md` / `collab_tasks.json` 为准。

---

## 4. 状态与象限

| 状态 | 含义 |
|------|------|
| `todo` | 未开始 |
| `doing` | 进行中 |
| `blocked` | 等主理人点验/拍板 |
| `parked` | 暂缓 |
| `done` | 已完成 |

象限：`Q1` 重要紧急 · `Q2` 重要不紧急 · `Q3` 紧急不重要 · `Q4` 其它

---

## 5. 协作约定

1. Agent 不得代清「主理人点验」类 gaps。  
2. 费用管理 / 算力账单禁止开工。  
3. 完成项：四象限勾选，并回写 `OPS-01-交接与进度.md` 与（如有）`collab_tasks.json` 的 `done`。  
4. 工程写法遵守 `docs/规范/STD-01-工程标准与流程.md`。
