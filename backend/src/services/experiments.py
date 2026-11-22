"""配对试验的应用服务：登记抽签单、跨系统对账与源数据更新后的重算。

本模块只依赖标准库与领域层，不直接 import ORM，方便在无数据库环境验证
「重算前撤下旧结论」等业务规则。持久化对象由 routes 层传入，只要具备
同名属性与 add/scalar 方法即可（鸭子类型）。
"""

import csv
import hashlib
import io
import json
from random import Random

from src.constants.enums import ConclusionState, ExperimentStatus
from src.domain.experiment import parse_draw, parse_recon, reconcile, run_experiment
from src.domain.experiment_spec import DRAW_FIELDS, RECON_FIELDS
from src.utils.time import now

_RNG_SEED = 20261122


def fingerprint(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _csv_rows(text, fields, noun):
    reader = csv.DictReader(io.StringIO(text.removeprefix("﻿"), newline=""), strict=True)
    keys = {field["key"] for field in fields}
    required = {field["key"] for field in fields if field.get("required", True)}
    headers = reader.fieldnames or []
    if not required <= set(headers) or not set(headers) <= keys or len(headers) != len(set(headers)):
        raise ValueError(f"{noun} CSV 表头与字段说明不符，请下载模板检查列名")
    rows = []
    try:
        for raw in reader:
            if None in raw or any(value is None for value in raw.values()):
                raise ValueError("工作表的列数与表头不一致")
            rows.append({key: (value.strip() if isinstance(value, str) else value)
                         for key, value in raw.items()})
    except csv.Error:
        raise ValueError(f"{noun} CSV 第 {reader.line_num} 行附近格式不正确") from None
    if not rows:
        raise ValueError(f"{noun} CSV 至少需要一行有效数据")
    return rows


def parse_draw_csv(text):
    """解析抽签单 CSV，返回校验通过的扁平行（register 内部再结构化）。"""
    rows = _csv_rows(text, DRAW_FIELDS, "抽签单")
    parse_draw(rows)
    return rows


def parse_recon_csv(text):
    # 空对账由领域层统一判定为全部缺窗
    rows = _csv_rows(text, RECON_FIELDS, "对账记录")
    parse_recon(rows)
    return rows


def draw_to_json(structured):
    """结构化抽签单转成可入库的 JSON（时间统一 ISO 字符串）。"""
    rows = []
    for pair in structured:
        for shift in pair["shifts"]:
            rows.append({
                "pair_id": pair["pair_id"], "group_name": pair["group_name"],
                "shift_id": shift["shift_id"],
                "window_start": shift["window_start"].isoformat(sep=" "),
                "window_end": shift["window_end"].isoformat(sep=" "),
                "scheme_order": shift["scheme_order"],
                "switch_at": shift["switch_at"].isoformat(sep=" "),
            })
    return rows


def register(db, name, draw_rows, warmup_minutes, permutations, actor):
    """登记抽签单。ORM 模型与查重查询在 routes 层通过 db 工厂注入。"""
    structured = parse_draw(draw_rows)
    checksum = fingerprint(draw_rows)
    existing = db.find_experiment_by_draw_checksum(checksum)
    if existing and existing.name == name:
        return existing, False
    item = db.create_experiment(
        name=name, draw_checksum=checksum, draw_rows=draw_to_json(structured),
        warmup_minutes=warmup_minutes, permutations=permutations,
        pair_count=len(structured), author=actor,
    )
    db.audit(actor, "experiment.registered", item.id, pairs=item.pair_count)
    return item, True


def _archive_active_conclusion(db, item, reason, actor):
    """重算前撤下旧结论：active → superseded，写审计，绝不就地覆盖。"""
    archived = db.find_active_conclusion(item.id)
    if not archived:
        return None
    archived.state = ConclusionState.SUPERSEDED
    archived.superseded_at = now()
    archived.reason = reason
    db.audit(actor, "experiment.conclusion_superseded", item.id,
             version=archived.version, reason=reason)
    return archived


def recompute(db, item, recon_rows, actor, reason="manual"):
    """源数据更新后的统一入口：先撤下旧结论，再用当前快照重算。"""
    recon_checksum = fingerprint(recon_rows)
    stale_reason = (f"源数据更新（{reason}），旧结论撤下，等待以对账指纹 {recon_checksum[:12]}… 重算")[:300]
    _archive_active_conclusion(db, item, stale_reason, actor)
    item.status = ExperimentStatus.STALE
    item.error = None
    try:
        result = run_experiment(item.draw_rows, recon_rows, item.warmup_minutes,
                                item.permutations, Random(_RNG_SEED))
    except ValueError as error:
        # 旧结论已在上面撤下；result 同步清空，避免页面继续展示失效数字
        item.result = None
        item.status = ExperimentStatus.FAILED
        item.error = str(error)[:500]
        item.recon_rows = recon_rows
        item.recon_checksum = recon_checksum
        item.updated_at = now()
        db.audit(actor, "experiment.recompute_failed", item.id, reason=str(error)[:300])
        return item
    item.result = result
    item.recon_rows = recon_rows
    item.recon_checksum = recon_checksum
    item.included_count = result["stats"]["included_pairs"]
    item.status = ExperimentStatus.COMPUTED
    item.computed_at = now()
    item.updated_at = now()
    version = db.next_conclusion_version(item.id)
    db.add_conclusion(
        experiment_id=item.id, version=version, state=ConclusionState.ACTIVE,
        draw_checksum=item.draw_checksum, recon_checksum=recon_checksum,
        result=result, reason=f"{reason} 重算"[:300], author=actor,
    )
    db.audit(actor, "experiment.recomputed", item.id, version=version,
             included=result["stats"]["included_pairs"],
             excluded=result["stats"]["excluded_pairs"],
             observed_difference=result["stats"]["observed_difference"],
             p_value=result["stats"]["p_value"])
    return item


def reconcile_only(item):
    """风险页查询：按当前对账快照重算排除清单，不产生新结论。"""
    if not item.recon_rows:
        return {"pairs": [{"pair_id": pair["pair_id"], "group_name": pair["group_name"],
                           "included": False,
                           "issues": ["尚无对账记录，两个班次均缺窗"],
                           "shifts": [{"shift_id": shift["shift_id"],
                                       "scheme_order": shift["scheme_order"],
                                       "switch_at": shift["switch_at"],
                                       "record_count": 0,
                                       "missing_sources": ["signal", "duty"]}
                                      for shift in pair["shifts"]]}
                          for pair in parse_draw(item.draw_rows)],
                "recon_checksum": None}
    pairs = reconcile(parse_draw(item.draw_rows),
                      parse_recon(item.recon_rows), item.warmup_minutes)
    return {"pairs": pairs, "recon_checksum": item.recon_checksum}
