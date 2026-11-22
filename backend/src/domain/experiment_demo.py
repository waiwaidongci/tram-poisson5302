"""配对信号方案试验的可复现演示数据：抽签单与跨系统对账记录。"""

from datetime import date, timedelta
from random import Random

from .experiment_spec import SCHEME_NEW, SCHEME_OLD

_PAIR_GROUPS = (
    ("P1", "港湾路-货栈街口", "旧-新", "新-旧"),
    ("P2", "港湾路-渡口街口", "新-旧", "旧-新"),
    ("P3", "科创大道-智造街口", "旧-新", "新-旧"),
    ("P4", "科创大道-东环街口", "新-旧", "旧-新"),
)


def demo_draw_rows():
    """每对相邻路口同组两个班次，08:00–10:00，09:00 切换方案。"""
    rows = []
    base = date(2026, 11, 19)
    for index, (pair_id, group, order_a, order_b) in enumerate(_PAIR_GROUPS):
        day = (base + timedelta(days=index)).isoformat()
        for shift_id, order in ((f"{pair_id}-甲", order_a), (f"{pair_id}-乙", order_b)):
            rows.append({
                "pair_id": pair_id, "group_name": group, "shift_id": shift_id,
                "window_start": f"{day} 08:00:00", "window_end": f"{day} 10:00:00",
                "scheme_order": order, "switch_at": f"{day} 09:00:00",
            })
    return rows


def _segments(order):
    # 旧段 08:00-09:00、热身 09:00-09:30、新段 09:30-10:00
    if order == "旧-新":
        return ((SCHEME_OLD, "08:00:00", "09:00:00"),
                (None, "09:00:00", "09:30:00"),
                (SCHEME_NEW, "09:30:00", "10:00:00"))
    return ((SCHEME_NEW, "08:00:00", "09:00:00"),
            (None, "09:00:00", "09:30:00"),
            (SCHEME_OLD, "09:30:00", "10:00:00"))


def demo_recon_rows(include_gap=False):
    """生成信号系统过车与值班系统阻断两套来源；include_gap 时 P4-乙 缺值班记录。"""
    rng = Random(261177)
    rows = []
    base = date(2026, 11, 19)
    for index, (pair_id, group, order_a, order_b) in enumerate(_PAIR_GROUPS):
        day = (base + timedelta(days=index)).isoformat()
        for shift_index, (shift_id, order) in enumerate((
                (f"{pair_id}-甲", order_a), (f"{pair_id}-乙", order_b))):
            for scheme, start, end in _segments(order):
                exposure = rng.randrange(80, 140)
                # 新方案阻断率系统性更低，热身段保持高阻断以验证其被剔除
                rate = 0.09 if scheme == SCHEME_OLD else 0.04 if scheme == SCHEME_NEW else 0.10
                blockage = _poisson(rng, exposure * rate)
                # 信号系统只报过车车次，值班系统只报阻断次数，各自不含对方字段
                rows.append({"pair_id": pair_id, "shift_id": shift_id, "source_system": "signal",
                             "record_start": f"{day} {start}", "record_end": f"{day} {end}",
                             "exposure": exposure})
                if include_gap and pair_id == "P4" and shift_id == "P4-乙":
                    continue
                rows.append({"pair_id": pair_id, "shift_id": shift_id, "source_system": "duty",
                             "record_start": f"{day} {start}", "record_end": f"{day} {end}",
                             "blockage": blockage})
    return rows


def _poisson(rng, mean):
    from math import exp
    limit = exp(-mean)
    product = rng.random()
    count = 0
    while product > limit:
        product *= rng.random()
        count += 1
    return count
