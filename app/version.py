# -*- coding: utf-8 -*-
"""TOA3 版本号（单一来源：发版前只改此处，打包/Portal/运营台须与此一致）。"""
APP_VERSION = "3.1.12"
APP_NAME = "TOA3"


def build_profile_label() -> str:
    """内部/关于页：开发构建标识（不对用户作为产品档位）。"""
    try:
        from services.user_plan_presentation import dev_build_tag

        tag = dev_build_tag()
        return tag or ""
    except Exception:
        return ""


def version_caption(*, short: bool = False, for_about: bool = False) -> str:
    """用户可见版本串（不含开发版/正式版/体验版等产品档位混称）。"""
    try:
        from services.user_plan_presentation import dev_build_tag, user_software_version, user_version_caption

        if short:
            base = user_software_version(short=True)
            if for_about and dev_build_tag():
                return f"{base} · {dev_build_tag()}"
            return base
        return user_version_caption(for_about=for_about)
    except Exception:
        return f"v{APP_VERSION}" if short else f"TOA3 v{APP_VERSION}"
