# -*- coding: utf-8 -*-
"""档位文案一致性：禁止「正式版·体验版」混称。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from services.user_plan_presentation import (
        EXPERIENCE_TIER_LABEL,
        OFFICIAL_TIER_LABEL,
        _join_unique_labels,
        _pack_for_join,
        _plan_name,
    )

    assert _plan_name("tiyan", entitlement="paid") == ""
    assert _plan_name("tiyan", entitlement="trial") == ""
    assert _pack_for_join(OFFICIAL_TIER_LABEL, "体验版") == ""
    assert _pack_for_join(OFFICIAL_TIER_LABEL, "全功能方案") == ""
    assert _pack_for_join(EXPERIENCE_TIER_LABEL, "体验版") == ""
    joined = _join_unique_labels(OFFICIAL_TIER_LABEL, _pack_for_join(OFFICIAL_TIER_LABEL, "体验版"))
    assert joined == OFFICIAL_TIER_LABEL, joined
    assert "体验版" not in joined or joined == EXPERIENCE_TIER_LABEL

    # 目录名不再对外叫体验版
    from services.feature_packs import list_packs

    for p in list_packs(sellable_only=False):
        if str(p.get("id") or "") == "tiyan":
            name = str(p.get("name") or "")
            assert name != "体验版", name
            break

    print("OK: plan labels consistent (no 正式版·体验版)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
