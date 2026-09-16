# -*- coding: utf-8 -*-
"""引擎共用唯一 QWebEngineView。

Harness / OpenPencil / Draw.io / Comfy 等：
  - 各自只负责启停与健康检查（不同 port / 命令）
  - 内嵌画面共用这一份 Chromium，切引擎 = 换 URL + 租借权
禁止每页各建一份 View（多 Chromium 叠崩 / 首进抖窗）。

闪烁根治要点：
  - 同 URL 不 Stop / 不 setUrl
  - 引擎↔引擎 handoff：不 hide、不 Stop、不进 holder
  - 离页软停靠：hide 归 holder；回嵌再 Active（禁止离屏常亮第二窗抢合成）
  - 仅离开引擎域 destroy 时才 Stop + 拆掉 View
"""
from __future__ import annotations

import logging
import weakref
from typing import Any, Callable

logger = logging.getLogger("TOA3.shared_webengine")

_holder: Any = None
_view: Any = None
_profile: Any = None
_owner_id: str | None = None
_owner_ref: weakref.ref | None = None
_load_cb: Callable[[bool], None] | None = None
_f11_filter: Any = None
_current_url: str = ""


def normalize_nav_url(url: str) -> str:
    """导航目标 URL：有 query/fragment 时禁止末尾再加 `/`（否则会破坏 `?token=`）。"""
    u = str(url or "").strip()
    if not u:
        return u
    if "?" in u or "#" in u:
        return u
    return u if u.endswith("/") else u + "/"


def _qt_alive(obj) -> bool:
    if obj is None:
        return False
    try:
        from shiboken6 import isValid

        return bool(isValid(obj))
    except Exception:
        try:
            obj.objectName()
            return True
        except RuntimeError:
            return False


def _ensure_holder():
    global _holder
    from PySide6.QtWidgets import QApplication, QWidget

    app = QApplication.instance()
    if app is None:
        return None
    if not _qt_alive(_holder):
        _holder = QWidget()
        _holder.setObjectName("ToaSharedLocalWebEngineHolder")
        # 隐藏停靠即可；勿离屏 show+Active（第二窗抢 DWM 合成 → 主窗内闪）
        _holder.hide()
        _holder.setParent(None)
    return _holder


def _wake_view(view) -> None:
    """回嵌时叫醒页面（Active），避免 Frozen 白闪一帧。"""
    if not _qt_alive(view):
        return
    try:
        from PySide6.QtWebEngineCore import QWebEnginePage

        page = view.page()
        if page is not None:
            try:
                page.setVisible(True)
            except Exception:
                pass
            try:
                page.setLifecycleState(QWebEnginePage.LifecycleState.Active)
            except Exception:
                pass
    except Exception:
        pass


def _park_view_quiet(view) -> None:
    """软停靠：hide 归 holder。禁止离屏常亮第二窗。"""
    from PySide6.QtWidgets import QApplication

    try:
        fw = QApplication.focusWidget()
        if fw is not None and (fw is view or view.isAncestorOf(fw)):
            fw.clearFocus()
    except Exception:
        pass
    try:
        view.hide()
    except Exception:
        pass
    holder = _ensure_holder()
    try:
        view.setParent(holder)
    except Exception:
        try:
            view.setParent(None)
        except Exception:
            pass
    if holder is not None:
        try:
            holder.hide()
        except Exception:
            pass


def _ensure_view():
    """懒创建唯一 View + Profile（进程内单例）。"""
    global _view, _profile
    if _qt_alive(_view):
        return _view
    # 先拆预热占位，禁止与真 View 双 Chromium 抖窗
    try:
        from services.webengine_prewarm import release_prewarm_hold

        release_prewarm_hold()
    except Exception:
        pass
    from PySide6.QtCore import Qt
    from PySide6.QtWebEngineCore import QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QSizePolicy

    from services.storage_paths import module_data_dir
    from services.webengine_host import ToaWebEnginePage, apply_webengine_view_defaults

    holder = _ensure_holder()
    if holder is None:
        return None

    if not _qt_alive(_profile):
        profile_dir = module_data_dir("local_web_engine", create=True) / "shared_browser_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        _profile = QWebEngineProfile("toa3_local_web_engines_shared", holder)
        _profile.setPersistentStoragePath(str(profile_dir))
        _profile.setCachePath(str(profile_dir / "cache"))

    _view = QWebEngineView(holder)
    page = ToaWebEnginePage(_profile, _view)
    _view.setPage(page)
    apply_webengine_view_defaults(_view)
    _view.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    _view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    _view.hide()
    logger.info("已创建共享引擎 WebEngine（单例 · Harness/OpenPencil/Draw 共用）")
    return _view


def current_owner_id() -> str | None:
    return _owner_id


def current_url() -> str:
    return _current_url


def painted_url() -> str:
    """View 当前文档 URL（可能与 current_url 短暂不一致：导航被 beforeunload 挡住时）。"""
    if not _qt_alive(_view):
        return ""
    try:
        return str(_view.url().toString() or "")
    except Exception:
        return ""


def live_view() -> Any:
    """返回存活的共享 View（只读借用；调用方勿 deleteLater）。"""
    return _view if _qt_alive(_view) else None


def has_live_view() -> bool:
    return _qt_alive(_view)


def _detach_prev_owner() -> None:
    """清掉上一租户的 Python 引用；不碰 View 可见性（交由 acquire/release）。"""
    global _owner_ref
    prev = None
    try:
        prev = _owner_ref() if _owner_ref is not None else None
    except Exception:
        prev = None
    if prev is None:
        return
    try:
        setattr(prev, "_view", None)
        setattr(prev, "_embedded_url", "")
        setattr(prev, "_web_embedded_ok", False)
        host = getattr(prev, "_host", None)
        if host is not None:
            if hasattr(host, "detach_view"):
                host.detach_view(hide=False)
            elif hasattr(host, "clear_view_ref"):
                host.clear_view_ref()
    except Exception:
        pass


def acquire(
    owner_id: str,
    url: str,
    *,
    host_ref=None,
    on_load_finished: Callable[[bool], None] | None = None,
    event_filter=None,
) -> Any:
    """把唯一 View 租给 owner；仅 URL 变化时导航。

    调用方负责把返回的 View 挂到自己的 stack（attach/embed）；
    本函数保证：同时最多一个租户、一份 Chromium；同 URL 不 Stop/不重载。
    """
    global _owner_id, _owner_ref, _load_cb, _f11_filter, _current_url

    oid = str(owner_id or "").strip()
    if not oid:
        return None
    logger.debug("acquire begin owner=%s url=%s prev_owner=%s", oid, url, _owner_id)
    view = _ensure_view()
    if view is None:
        logger.warning("acquire 失败：无 View owner=%s", oid)
        return None

    # 其它租户：软交接（不 hide / 不 Stop），避免引擎↔引擎白闪
    if _owner_id and _owner_id != oid:
        _detach_prev_owner()
        release(_owner_id, destroy=False, park=False)

    # 同租户重入：仅在回调变化时重绑，避免每 4s 轮询 disconnect 抖动
    same_cb = on_load_finished is not None and on_load_finished is _load_cb
    if _load_cb is not None and not same_cb:
        try:
            view.loadFinished.disconnect(_load_cb)
        except Exception:
            pass
        _load_cb = None
    if _f11_filter is not None and event_filter is not _f11_filter:
        try:
            view.removeEventFilter(_f11_filter)
        except Exception:
            pass
        _f11_filter = None

    _owner_id = oid
    try:
        _owner_ref = weakref.ref(host_ref) if host_ref is not None else None
    except Exception:
        _owner_ref = None

    if event_filter is not None and event_filter is not _f11_filter:
        try:
            view.installEventFilter(event_filter)
            _f11_filter = event_filter
        except Exception:
            _f11_filter = None

    if on_load_finished is not None and on_load_finished is not _load_cb:
        try:
            view.loadFinished.connect(on_load_finished)
            _load_cb = on_load_finished
        except Exception:
            _load_cb = None

    if url:
        from PySide6.QtCore import QUrl

        from services.webengine_host import ToaWebEnginePage

        nav = normalize_nav_url(url)
        # 比较时去掉末尾 `/`，但保留 query（token URL 不能用 rstrip 后乱拼）
        cur_key = _current_url.split("#", 1)[0].rstrip("/")
        nav_key = nav.split("#", 1)[0].rstrip("/")
        need_nav = cur_key != nav_key
        if need_nav:
            _current_url = nav
            page = view.page()
            # Draw.io 等会弹 beforeunload；不放行则壳已切引擎、画面仍卡旧站
            if isinstance(page, ToaWebEnginePage):
                page.begin_forced_navigation()
            else:
                try:
                    page.runJavaScript(
                        "try{window.onbeforeunload=null;}catch(e){}"
                    )
                except Exception:
                    pass
            view.setUrl(QUrl(nav))
            logger.debug("acquire navigate owner=%s url=%s", oid, nav)
        else:
            logger.debug("acquire keep url owner=%s", oid)
    # 同 URL 回嵌也必须叫醒：park 后可能被系统标 Frozen
    _wake_view(view)
    return view


def release(owner_id: str, *, destroy: bool = False, park: bool = True) -> None:
    """归还租借。

    - destroy=True：离开引擎域，Stop + 延迟 deleteLater
    - park=True：离页软停靠到离屏 holder（保持清醒，禁止 hide 冻住）
    - park=False：引擎 handoff，只清租约，View 保持现状给下一租户
    """
    global _owner_id, _owner_ref, _load_cb, _f11_filter, _view, _current_url

    oid = str(owner_id or "").strip()
    if _owner_id and oid and _owner_id != oid:
        logger.debug("release skip owner=%s current=%s", oid, _owner_id)
        return

    logger.debug(
        "release owner=%s destroy=%s park=%s live=%s",
        oid or _owner_id,
        destroy,
        park,
        _qt_alive(_view),
    )
    view = _view
    if _load_cb is not None and _qt_alive(view):
        try:
            view.loadFinished.disconnect(_load_cb)
        except Exception:
            pass
    _load_cb = None
    if _f11_filter is not None and _qt_alive(view):
        try:
            view.removeEventFilter(_f11_filter)
        except Exception:
            pass
    _f11_filter = None

    if destroy and _qt_alive(view):
        try:
            from PySide6.QtWidgets import QApplication

            fw = QApplication.focusWidget()
            if fw is not None and (fw is view or view.isAncestorOf(fw)):
                fw.clearFocus()
        except Exception:
            pass
        try:
            from PySide6.QtWebEngineCore import QWebEnginePage

            page = view.page()
            if page is not None:
                page.triggerAction(QWebEnginePage.WebAction.Stop)
                try:
                    page.setLifecycleState(QWebEnginePage.LifecycleState.Discarded)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            view.hide()
        except Exception:
            pass
        holder = _ensure_holder()
        try:
            view.setParent(holder)
        except Exception:
            try:
                view.setParent(None)
            except Exception:
                pass
    elif park and _qt_alive(view):
        # 软停靠：hide 归 holder（禁止离屏 Active 第二窗 → 主窗内闪）
        _park_view_quiet(view)
    # park=False：handoff，不动 View

    _owner_id = None
    _owner_ref = None

    if destroy and _qt_alive(view):
        from PySide6.QtCore import QTimer

        v = view
        _view = None
        _current_url = ""
        # 稍长一点：业务页 DataTable 与 Chromium 析构重叠会 AV
        QTimer.singleShot(600, lambda: _delete_view_later(v))


def _delete_view_later(view) -> None:
    if not _qt_alive(view):
        return
    try:
        view.setPage(None)
    except Exception:
        pass
    try:
        view.deleteLater()
    except Exception:
        pass


def shutdown() -> None:
    """进程退出 / 离开引擎域前调用。"""
    global _owner_id
    logger.info("shared_webengine shutdown owner=%s live=%s", _owner_id, has_live_view())
    if _owner_id:
        release(_owner_id, destroy=True)
    else:
        release("", destroy=True)
