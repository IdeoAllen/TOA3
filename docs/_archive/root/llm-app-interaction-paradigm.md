# 大模型应用 · 极简交互范式

> 状态：`approved` · 经主理人确认（2026-09-03）  
> Figma：https://www.figma.com/design/fF227FGOtqn1EE2rpS7jmi  
> 对齐：`product.yml` 双门槛引导 · `docs/architecture/19-AI子模块与多模态模型中枢.md`

## 1. 一句话

**应用时选模型；简单配置持久化（≤2 步）。** 业务页不堆 API 表单。

## 2. 两柱

| 柱 | 何时 | 用户动作 | 持久？ |
|----|------|----------|--------|
| **① 选模型** | 每次应用（生成前） | 任务页顶栏下拉点选 | 切换即记为默认 |
| **② 简单配置** | 首次 / 「简单配置…」/ 「＋绑定」 | ① 选算力来源 ② Key 或本机模型名 → 保存 | 是（本机 user 配置） |

## 3. 心智分层

```
小白（已有默认）     打开 → 输入 → 生成
有条件探索           「简单配置…」→ 两步保存 → 之后同小白
应用时换模型         不下钻设置，顶栏下拉点选即用
```

## 3.5 独到之处（经主理人论证 · 恰好 3 条）

1. **应用时选模型，配置不上任务页** — 用户可感知：生成前一行下拉即可换卡；验收：业务页无 URL/多字段 API 表单。  
2. **简单配置恰好两步且可跳过** — 选来源 + Key（或本机模型名）；空态可「稍后再说」；验收：弹窗步骤≤2，未绑定仍可浏览页面。  
3. **一件绑定、自动持久默认** — 保存后设为默认，下次打开零配置；验收：`set_active_profile_id` + secrets 落盘，重进页仍选中该模型。

## 4. 屏对照（Figma → 代码）

| 帧 | 落地 |
|----|------|
| A 应用态 | `llm_assistant_page`：选模型条 + 输入 + 生成 + 结果 |
| B 选模型展开 | ComboBox +「＋ 绑定新模型…」 |
| C 首次空态 | `_empty_panel`：开始两步 / 稍后再说 |
| D 简单配置 | `LlmSimpleSetupDialog` |

## 5. 禁止

- 业务页出现 URL / 多字段 API 表单  
- 配置超过 2 步且无逐步引导  
- 未绑模型时阻断浏览（应可稍后再说）

## 6. 代码落点

- `modules/llm_assistant/llm_assistant_page.py`  
- `modules/llm_assistant/llm_simple_setup_dialog.py`（`bind_text_llm_simple`）  
- 自测：`scripts/verify_llm_simple_paradigm.py`
