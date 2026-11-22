"""配对信号方案试验：跨系统对账、窗口排除与整组置换检验。

设计约束（与调度口径一致）：
- 分析单位是一对相邻路口同组的两个班次；抽签单决定每班旧/新方案顺序。
- 过车量来自信号系统、阻断事件来自值班系统，按抽签单跨系统对账。
- 切换后 warmup_minutes 分钟为热身窗，不计入任何方案。
- 任一班缺窗（缺少来源、覆盖不全、时间不一致）整对不纳入。
- 置换检验只能整组交换两班标签，即对每一对整体翻转旧/新归属。
"""

from collections import defaultdict
from datetime import datetime, timedelta
from math import fsum, isclose

from .experiment_spec import (
    DRAW_FIELDS, EXACT_ENUMERATION_LIMIT, MAX_DRAW_ROWS, MAX_RECON_ROWS,
    RECON_FIELDS, SCHEME_NEW, SCHEME_OLD,
)


def _parse_stamp(raw):
    if not isinstance(raw, str):
        raise ValueError("时间须为 YYYY-MM-DD HH:MM:SS 文本")
    text = raw.strip().replace("T", " ")
    if text.endswith("Z"):
        text = text[:-1]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"时间 {raw!r} 不是有效的 YYYY-MM-DD HH:MM:SS")


def _validate(field, value):
    kind = field["type"]
    label = field["label"]
    if kind == "datetime":
        return _parse_stamp(value)
    if kind == "int":
        # CSV 通道给出的是字符串，先归一化为整数；布尔值不属于合法计数
        if isinstance(value, bool):
            raise ValueError(f"{label}须为 {field['min']} 至 {field['max']} 之间的整数")
        if isinstance(value, str):
            text = value.strip()
            if not text or any(ch in text for ch in (".", "e", "E")):
                raise ValueError(f"{label}须为整数")
            try:
                value = int(text)
            except ValueError:
                raise ValueError(f"{label}须为整数") from None
        if not isinstance(value, int) or not field["min"] <= value <= field["max"]:
            raise ValueError(f"{label}须为 {field['min']} 至 {field['max']} 之间的整数")
        return value
    if kind == "select":
        if value not in field["options"]:
            raise ValueError(f"{label}须为{'、'.join(field['options'])}之一")
        return value
    if not isinstance(value, str) or not value.strip() or len(value) > field["max_length"]:
        raise ValueError(f"{label}须为非空文本，最多 {field['max_length']} 字符")
    return value.strip()


def _check(fields, rows, limit, noun):
    if not isinstance(rows, (list, tuple)) or not 1 <= len(rows) <= limit:
        raise ValueError(f"{noun}须包含 1 至 {limit} 行")
    cleaned = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"{noun}第 {index} 行须为一条记录")
        try:
            item = {}
            for field in fields:
                present = field["key"] in row and row[field["key"]] not in (None, "")
                if field.get("required", True):
                    if not present:
                        raise ValueError(f"{field['label']}不能为空")
                    item[field["key"]] = _validate(field, row[field["key"]])
                elif present:
                    item[field["key"]] = _validate(field, row[field["key"]])
            cleaned.append(item)
        except ValueError as error:
            raise ValueError(f"{noun}第 {index} 行 · {error}") from None
    return cleaned


def parse_draw(rows):
    cleaned = _check(DRAW_FIELDS, rows, MAX_DRAW_ROWS, "抽签单")
    pairs = defaultdict(dict)
    meta = {}
    for item in cleaned:
        pair_id, shift_id = item["pair_id"], item["shift_id"]
        if shift_id in pairs[pair_id]:
            raise ValueError(f"配对 {pair_id} 的班次 {shift_id} 在抽签单中重复")
        if not item["window_start"] < item["window_end"]:
            raise ValueError(f"配对 {pair_id} 班次 {shift_id} 的开始时间须早于结束时间")
        if not item["window_start"] <= item["switch_at"] < item["window_end"]:
            raise ValueError(f"配对 {pair_id} 班次 {shift_id} 的切换时间须落在班次窗口内")
        pairs[pair_id][shift_id] = item
        meta.setdefault(pair_id, item["group_name"])
        if meta[pair_id] != item["group_name"]:
            raise ValueError(f"配对 {pair_id} 的相邻路口同组名称不一致")
    structured = []
    for pair_id, shifts in pairs.items():
        if len(shifts) != 2:
            raise ValueError(f"配对 {pair_id} 须恰好包含两个班次，当前为 {len(shifts)} 个")
        windows = list(shifts.values())
        if windows[0]["window_start"] != windows[1]["window_start"] or \
           windows[0]["window_end"] != windows[1]["window_end"]:
            raise ValueError(f"配对 {pair_id} 的两个班次窗口起止时间不一致，无法成对比较")
        structured.append({
            "pair_id": pair_id, "group_name": meta[pair_id],
            "shifts": sorted(shifts.values(), key=lambda entry: entry["shift_id"]),
        })
    structured.sort(key=lambda entry: (entry["shifts"][0]["window_start"], entry["pair_id"]))
    return structured


def parse_recon(rows):
    if not isinstance(rows, (list, tuple)) or len(rows) > MAX_RECON_ROWS:
        raise ValueError(f"对账记录最多包含 {MAX_RECON_ROWS} 行")
    indexed = defaultdict(lambda: defaultdict(list))
    if not rows:
        return indexed
    cleaned = _check(RECON_FIELDS, rows, MAX_RECON_ROWS, "对账记录")
    for item in cleaned:
        if not item["record_start"] < item["record_end"]:
            raise ValueError(
                f"配对 {item['pair_id']} 班次 {item['shift_id']} 的记录开始时间须早于结束时间")
        indexed[item["pair_id"]][item["shift_id"]].append(item)
    return indexed


def _segments(shift, warmup_minutes):
    """按切换时点把班次切成旧方案、热身、新方案三段。"""
    switch = shift["switch_at"]
    warmup_end = switch + timedelta(minutes=warmup_minutes)
    order = shift["scheme_order"]
    if order == "旧-新":
        first, second = SCHEME_OLD, SCHEME_NEW
    else:
        first, second = SCHEME_NEW, SCHEME_OLD
    segments = [
        {"scheme": first, "start": shift["window_start"], "end": switch, "warmup": False},
        {"scheme": None, "start": switch, "end": min(warmup_end, shift["window_end"]), "warmup": True},
    ]
    if warmup_end < shift["window_end"]:
        segments.append({"scheme": second, "start": warmup_end, "end": shift["window_end"], "warmup": False})
    return [segment for segment in segments if segment["start"] < segment["end"]]


def _overlap_minutes(start_a, end_a, start_b, end_b):
    return max(0.0, (min(end_a, end_b) - max(start_a, start_b)).total_seconds() / 60.0)


def _attribute(records, shift, warmup_minutes):
    """把一个班次的跨系统记录归到方案段，返回 (各方案聚合, 问题清单, 热身明细)。"""
    schemes = {SCHEME_OLD: {"exposure": 0, "blockage": 0, "minutes": 0.0},
               SCHEME_NEW: {"exposure": 0, "blockage": 0, "minutes": 0.0}}
    issues, warmup = [], []
    for record in records:
        covered = []
        for segment in _segments(shift, warmup_minutes):
            overlap = _overlap_minutes(record["record_start"], record["record_end"],
                                       segment["start"], segment["end"])
            if overlap <= 0:
                continue
            covered.append((segment, overlap))
        segment_minutes = sum(overlap for _, overlap in covered)
        record_minutes = (record["record_end"] - record["record_start"]).total_seconds() / 60.0
        if not covered or not isclose(segment_minutes, record_minutes, rel_tol=0.0, abs_tol=1e-6):
            issues.append(f"来源 {record['source_system']} 记录 {record['record_start']:%Y-%m-%d %H:%M}–"
                          f"{record['record_end']:%H:%M} 超出抽签班次窗口")
            continue
        exposure = record.get("exposure")
        blockage = record.get("blockage")
        for segment, overlap in covered:
            share = overlap / segment_minutes
            if segment["warmup"]:
                warmup.append({"source": record["source_system"], "minutes": overlap,
                               "exposure": round((exposure or 0) * share),
                               "blockage": round((blockage or 0) * share)})
                continue
            bucket = schemes[segment["scheme"]]
            bucket["minutes"] += overlap
            if exposure is not None:
                bucket["exposure"] += round(exposure * share)
            if blockage is not None:
                bucket["blockage"] += round(blockage * share)
    return schemes, issues, warmup


def reconcile(draw, recon_index, warmup_minutes):
    pair_rows = []
    for pair in draw:
        pair_id = pair["pair_id"]
        issue_list = []
        shift_views = []
        scheme_totals = {SCHEME_OLD: {"exposure": 0, "blockage": 0},
                         SCHEME_NEW: {"exposure": 0, "blockage": 0}}
        warmup_total = {"exposure": 0, "blockage": 0, "minutes": 0.0}
        for shift in pair["shifts"]:
            shift_id = shift["shift_id"]
            records = recon_index.get(pair_id, {}).get(shift_id, [])
            sources = {record["source_system"] for record in records}
            missing = [name for name, code in (("信号系统过车", "signal"), ("值班系统阻断", "duty"))
                       if code not in sources]
            if missing:
                issue_list.append(f"班次 {shift_id} 缺少{'、'.join(missing)}记录")
            schemes, issues, warmup = _attribute(records, shift, warmup_minutes)
            issue_list.extend(f"班次 {shift_id} · {text}" for text in issues)
            for scheme, bucket in schemes.items():
                if bucket["minutes"] <= 0:
                    issue_list.append(f"班次 {shift_id} 没有落入{scheme}的有效窗（可能全部处于热身期）")
                scheme_totals[scheme]["exposure"] += bucket["exposure"]
                scheme_totals[scheme]["blockage"] += bucket["blockage"]
            for item in warmup:
                warmup_total["exposure"] += item["exposure"]
                warmup_total["blockage"] += item["blockage"]
                warmup_total["minutes"] += item["minutes"]
            shift_views.append({"shift_id": shift_id, "scheme_order": shift["scheme_order"],
                                "switch_at": shift["switch_at"].isoformat(sep=" "),
                                "record_count": len(records), "missing_sources": missing})
        for scheme, bucket in scheme_totals.items():
            if bucket["exposure"] <= 0:
                issue_list.append(f"{scheme}没有有效过车车次，无法计算每百车次阻断率")
        included = not issue_list
        pair_rows.append({
            "pair_id": pair_id, "group_name": pair["group_name"],
            "included": included, "issues": issue_list,
            "shifts": shift_views,
            "old_exposure": scheme_totals[SCHEME_OLD]["exposure"],
            "old_blockage": scheme_totals[SCHEME_OLD]["blockage"],
            "new_exposure": scheme_totals[SCHEME_NEW]["exposure"],
            "new_blockage": scheme_totals[SCHEME_NEW]["blockage"],
            "warmup_exposure": warmup_total["exposure"],
            "warmup_blockage": warmup_total["blockage"],
            "warmup_minutes": round(warmup_total["minutes"], 2),
        })
    return pair_rows


def _rate(blockage, exposure):
    return 100.0 * blockage / exposure if exposure > 0 else None


def _statistic(included, flipped_pairs):
    """整组翻转指定配对的两班标签后，旧/新每百车次阻断率之差。"""
    old_block = old_exp = new_block = new_exp = 0
    for row in included:
        flip = row["pair_id"] in flipped_pairs
        old_block += row["new_blockage"] if flip else row["old_blockage"]
        old_exp += row["new_exposure"] if flip else row["old_exposure"]
        new_block += row["old_blockage"] if flip else row["new_blockage"]
        new_exp += row["old_exposure"] if flip else row["new_exposure"]
    if old_exp <= 0 or new_exp <= 0:
        return None, _rate(old_block, old_exp), _rate(new_block, new_exp)
    old_rate = _rate(old_block, old_exp)
    new_rate = _rate(new_block, new_exp)
    return old_rate - new_rate, old_rate, new_rate


def permutation_test(pair_rows, permutations, rng):
    included = [row for row in pair_rows if row["included"]]
    excluded = [row for row in pair_rows if not row["included"]]
    observed, old_rate, new_rate = _statistic(included, frozenset())
    n = len(included)
    if n == 0 or observed is None:
        raise ValueError("没有任何配对通过对账，请先在风险页补齐缺窗后再试算")
    pair_ids = [row["pair_id"] for row in included]
    # 单配对差异用于核对整组交换的可加结构
    pair_diffs = []
    for row in included:
        pair_old = _rate(row["old_blockage"], row["old_exposure"])
        pair_new = _rate(row["new_blockage"], row["new_exposure"])
        pair_diffs.append({"pair_id": row["pair_id"], "old_rate": pair_old, "new_rate": pair_new,
                           "difference": None if pair_old is None or pair_new is None
                           else pair_old - pair_new})
    if n <= EXACT_ENUMERATION_LIMIT:
        distribution = []
        for number in range(1 << n):
            flipped = frozenset(pair_ids[i] for i in range(n) if number & (1 << i))
            statistic, _, _ = _statistic(included, flipped)
            if statistic is None:
                raise ValueError("整组交换后出现零车次方案，请核对纳入配对的暴露量")
            distribution.append(statistic)
        draws = len(distribution)
        method = f"精确枚举全部 {draws} 种整组交换（2^{n}）"
    else:
        draws = permutations + 1
        distribution = [observed]
        for _ in range(permutations):
            flipped = frozenset(pair_id for pair_id in pair_ids if rng.random() < 0.5)
            statistic, _, _ = _statistic(included, flipped)
            if statistic is None:
                raise ValueError("整组交换后出现零车次方案，请核对纳入配对的暴露量")
            distribution.append(statistic)
        method = f"固定随机种子蒙特卡洛 {permutations} 次整组交换（含观测排列共 {draws} 次）"
    extreme = sum(abs(value) >= abs(observed) - 1e-12 for value in distribution)
    p_value = extreme / draws
    return {
        "included_pairs": n, "excluded_pairs": len(excluded),
        "observed_difference": observed,
        "old_rate": old_rate, "new_rate": new_rate,
        "per_pair": sorted(pair_diffs, key=lambda item: item["pair_id"]),
        "p_value": p_value, "permutation_draws": draws, "method": method,
        "mean_pair_difference": fsum(item["difference"] for item in pair_diffs
                                     if item["difference"] is not None) / n,
        "reduces_blockage": observed > 0,
    }


def run_experiment(draw_rows, recon_rows, warmup_minutes, permutations, rng):
    if not isinstance(warmup_minutes, int) or not 0 <= warmup_minutes <= 240:
        raise ValueError("热身时长须为 0 至 240 分钟之间的整数")
    if not isinstance(permutations, int) or not 99 <= permutations <= 99999:
        raise ValueError("置换次数须为 99 至 99999 之间的整数")
    draw = parse_draw(draw_rows)
    recon_index = parse_recon(recon_rows)
    pair_rows = reconcile(draw, recon_index, warmup_minutes)
    stats = permutation_test(pair_rows, permutations, rng)
    old_exp = sum(row["old_exposure"] for row in pair_rows if row["included"])
    new_exp = sum(row["new_exposure"] for row in pair_rows if row["included"])
    old_block = sum(row["old_blockage"] for row in pair_rows if row["included"])
    new_block = sum(row["new_blockage"] for row in pair_rows if row["included"])
    headline = (
        f"纳入 {stats['included_pairs']} 对、排除 {stats['excluded_pairs']} 对；"
        f"旧方案 {old_rate_text(old_rate := stats['old_rate'])}，新方案 {old_rate_text(stats['new_rate'])}，"
        f"每百车次阻断差 {stats['observed_difference']:.4g}（正值表示新方案更少），"
        f"整组置换 p={stats['p_value']:.4f}。"
    )
    return {
        "headline": headline,
        "note": (f"热身窗为切换后 {warmup_minutes} 分钟，期间记录不计入任何方案；"
                 f"任一班缺窗则整对不纳入。置换检验{stats['method']}，只允许整组交换两班标签。"),
        "stats": stats,
        "pairs": pair_rows,
        "totals": {"old_exposure": old_exp, "new_exposure": new_exp,
                   "old_blockage": old_block, "new_blockage": new_block},
    }


def old_rate_text(rate):
    return f"{rate:.4g} 次阻断／百车次"
