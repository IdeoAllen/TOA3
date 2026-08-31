# -*- coding: utf-8 -*-
"""用户扩展沙箱：插件只落在本机 TOA 用户区，不得改安装包/系统。"""
from __future__ import annotations

from pathlib import Path

from services.config_service import project_root, resolve_path


def ensure_extensions_home() -> Path:
    """确保扩展主目录存在，并写入给用户看的说明（多扩展分管）。"""
    root = user_extensions_root()
    readme = root / "README.md"
    # 始终刷新说明，保证「我的扩展」口径与升级不冲数据区一致
    readme.write_text(
        "# TOA · 我的扩展区\n\n"
        "本目录属于**当前用户自己的 TOA**，与安装包分离。默认挂到顶栏 **业务**。\n\n"
        "## 小白怎么用\n\n"
        "1. 在智能体点「一句话扩展」，或说：「帮我做一个××，放到业务」\n"
        "2. 或在 TOA 顶栏 **系统 → 扩展** 里添加，再点「开发」\n"
        "3. 做好后点「打开」→ 顶栏 **业务**；不要了点「移除」\n\n"
        "## 规则\n\n"
        "- 每个扩展一个子文件夹：`<扩展id>/`\n"
        "- 子文件夹内必须有 `plugin.toml` + `AGENTS.md`\n"
        "- 开发时 **只打开某一个扩展的根目录**，不要打开本上级目录\n"
        "- 隐藏/移除登记不影响官方功能与智能体\n"
        "- **禁止**把扩展放到 TOA 安装目录或源码目录\n"
        "- 软件升级**不会清空**本目录（安装包不含用户扩展）\n\n"
        f"路径：`{root}`\n",
        encoding="utf-8",
    )
    return root


def list_extension_dirs() -> list[Path]:
    """扫描本机扩展区下已有扩展根（含 plugin.toml）。"""
    root = ensure_extensions_home()
    out: list[Path] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir():
            continue
        if (child / "plugin.toml").is_file() or (child / "plugin.yml").is_file():
            out.append(child.resolve())
    return out


def user_data_root() -> Path:
    return resolve_path("data_dir").resolve()


def user_extensions_root() -> Path:
    """本机扩展根目录（只属于当前用户的 TOA 数据区）。"""
    root = user_data_root() / "user" / "extensions"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def default_plugin_root(plugin_id: str) -> Path:
    pid = str(plugin_id or "").strip()
    return user_extensions_root() / pid


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except (ValueError, OSError):
        return False


def is_under_app_tree(path: Path | str) -> bool:
    """是否落在 TOA 工程/安装树内（含 data）。"""
    return _is_relative_to(Path(path), project_root())


def is_under_user_data(path: Path | str) -> bool:
    return _is_relative_to(Path(path), user_data_root())


def is_bundled_sample(path: Path | str) -> bool:
    sample = project_root() / "assets" / "samples" / "toa_plugin_pack"
    return _is_relative_to(Path(path), sample)


def is_app_source_or_install_code(path: Path | str) -> bool:
    """源码/安装资源（app、modules、plugin、config…）——禁止放用户扩展。"""
    p = Path(path).expanduser().resolve()
    if not is_under_app_tree(p):
        return False
    if is_under_user_data(p):
        return False
    if is_bundled_sample(p):
        return False
    # 打包后 data 可能在安装目录旁；仍允许 user data
    return True


def is_safe_extension_root(path: Path | str) -> bool:
    p = Path(path).expanduser().resolve()
    if is_under_user_data(p):
        return True
    if is_bundled_sample(p):
        return True
    if is_app_source_or_install_code(p):
        return False
    return True


def resolve_plugin_workspace(path: Path | str) -> Path:
    """选文件夹时向上查找 plugin.toml，避免误把 modules/ 当工作区。"""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise ValueError(f"路径不存在：{p}")
    cur = p if p.is_dir() else p.parent
    for _ in range(6):
        if (cur / "plugin.toml").is_file() or (cur / "plugin.yml").is_file():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return p if p.is_dir() else p.parent


def assert_registerable_root(path: Path | str, *, allow_sample: bool = True) -> Path:
    """导入登记前：拒绝落在宿主源码区的自研插件（样例除外）。"""
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        raise ValueError(f"插件根目录不存在：{p}")
    if is_bundled_sample(p) and allow_sample:
        return p
    if is_app_source_or_install_code(p):
        raise ValueError(
            "禁止把扩展放在 TOA 源码/安装程序目录内（会危及宿主）。\n"
            f"请改到本机用户扩展区：{user_extensions_root()}\n"
            "可用「系统 → 扩展」一键创建到安全目录。"
        )
    unsafe_prefixes = (
        Path(r"C:\Windows").resolve(),
        Path(r"C:\Program Files").resolve(),
        Path(r"C:\Program Files (x86)").resolve(),
    )
    for prefix in unsafe_prefixes:
        if _is_relative_to(p, prefix):
            raise ValueError(f"禁止在系统目录放置扩展：{prefix}")
    return p


def isolation_rules_text(*, plugin_id: str) -> str:
    ext = user_extensions_root()
    root = ext / plugin_id
    toa = project_root()
    return f"""## 隔离与安全（最高优先级）

**唯一工作区（绝对路径）**：`{root}`  
所有 Read / Grep / Write / Edit / Shell **只能**落在此目录内。

1. **禁止读宿主源码**（哪怕只读）：不得打开  
   `{toa}\\widgets\\*`、`{toa}\\core\\*`、`{toa}\\services\\*`、`{toa}\\app\\*`、  
   `{toa}\\modules\\*`（官方模块）、`{toa}\\config\\*`、安装目录、其它扩展。  
   API 已写在本目录 `AGENTS.md` / `HOST_API.md`，**不要**去扫宿主确认。
2. **禁止全盘搜索**：不得在 `Program Files`、`AppData`、桌面整盘、其它盘符、`C:\\` 根下递归找文件。
3. **禁止改宿主**：不得写入上述宿主路径、`.cursor/`、智能体安装目录。
4. **禁止影响本机**：不得动注册表、启动项、系统目录、未声明的联网与 shell。
5. **落盘**：代码只在扩展根；运行数据 `module_data_dir("{plugin_id}")`，输出 `module_output_dir("{plugin_id}")`。
6. **只作用于当前用户的 TOA**：登记在 `data/user/plugins.yml`；移除不影响官方功能。
"""
