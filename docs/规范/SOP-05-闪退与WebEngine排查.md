# SOP-05 · 闪退与 WebEngine 排查

> **编号**：SOP-05 · **Skill**：`toa3-sop-debug-crash`  
> **依据**：STD-01 · A4 · ARCH-08 · ARCH-05

## 1. 目的

系统化排查主窗闪退、抖窗、内嵌 Web 不清晰/点不动。

## 2. 步骤摘要

1. 开 DEBUG / 读 `common/logs/toa3.log` 与 faulthandler（若有）  
2. 区分：主进程崩溃 · Guest 崩溃 · 焦点/DPR/多 Chromium  
3. 复现最小路径；对照 ARCH-08 主子窗隔离、ARCH-05 默认 browser  
4. 修复须遵守 A4（禁进页同步重活；worker 不改控件）  
5. 回归：`verify_shell_hardening` 等（见 `verify_all`）  

## 3. 详细剧本

以 Skill `toa3-sop-debug-crash`（原 `toa3-sop-debug-crash`）内步骤为准。
