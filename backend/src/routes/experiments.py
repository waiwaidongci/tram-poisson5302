"""信号方案配对试验接口。

- 抽签单与对账模板下载
- 登记抽签单、上传对账记录触发重算（重算前撤下旧结论）
- 风险页：配对纳入/排除清单与缺窗原因，不依赖当前结论是否有效
- 结论历史：每次撤下与重算都留痕
原阻断预测（/runs）链路不受影响，照常使用。
"""

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config.database import connection
from src.constants.enums import Role
from src.controllers.auth import allow, current
from src.domain.experiment_spec import DRAW_FIELDS, RECON_FIELDS
from src.models.experiment import Experiment, ExperimentConclusion
from src.models.identity import User
from src.schemas.requests import ExperimentReconRequest, ExperimentRequest
from src.services import experiments as service
from src.services.experiment_gateway import ExperimentGateway
from src.utils import views

router = APIRouter(prefix='/experiments')


def require_experiment(db, experiment_id):
    item = db.get(Experiment, experiment_id)
    if not item:
        raise HTTPException(404, '找不到该配对试验')
    return item


def _template(fields, filename):
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer)
    writer.writerow([field['key'] for field in fields])
    return Response('﻿' + buffer.getvalue(), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{filename}"})


@router.get('/draw-template')
def draw_template(actor: User = Depends(current)):
    return _template(DRAW_FIELDS, 'draw-template.csv')


@router.get('/recon-template')
def recon_template(actor: User = Depends(current)):
    return _template(RECON_FIELDS, 'recon-template.csv')


@router.get('')
def index(db: Session = Depends(connection), actor: User = Depends(current)):
    items = db.scalars(select(Experiment).order_by(Experiment.id.desc()).limit(100))
    return [views.experiment(item) for item in items]


@router.post('', status_code=201)
def create(body: ExperimentRequest, db: Session = Depends(connection),
           actor: User = Depends(allow(Role.ADMIN, Role.ANALYST))):
    try:
        draw_rows = service.parse_draw_csv(body.draw_csv)
        item, created = service.register(
            ExperimentGateway(db), body.name, draw_rows,
            body.warmup_minutes, body.permutations, actor.username)
        db.commit()
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    return {**views.experiment(item, detail=True), 'created': created}


@router.get('/{experiment_id}')
def detail(experiment_id: int, db: Session = Depends(connection), actor: User = Depends(current)):
    return views.experiment(require_experiment(db, experiment_id), detail=True)


@router.post('/{experiment_id}/reconcile')
def reconcile_upload(experiment_id: int, body: ExperimentReconRequest,
                     db: Session = Depends(connection),
                     actor: User = Depends(allow(Role.ADMIN, Role.ANALYST))):
    item = require_experiment(db, experiment_id)
    try:
        # 先完整解析，避免坏数据把试验置为 stale 后又重算失败
        recon_rows = service.parse_recon_csv(body.recon_csv)
        service.recompute(ExperimentGateway(db), item, recon_rows, actor.username,
                          reason=body.reason)
        db.commit()
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    return views.experiment(item, detail=True)


@router.get('/{experiment_id}/risk')
def risk(experiment_id: int, db: Session = Depends(connection), actor: User = Depends(current)):
    """风险页：哪对没纳入、缺了什么。即使结论已撤下也照常可查。"""
    item = require_experiment(db, experiment_id)
    report = service.reconcile_only(item)
    excluded = [row for row in report['pairs'] if not row['included']]
    return {
        'experiment_id': item.id, 'name': item.name, 'status': item.status,
        'warmup_minutes': item.warmup_minutes,
        'recon_checksum': report['recon_checksum'],
        'pair_count': len(report['pairs']),
        'included_count': sum(1 for row in report['pairs'] if row['included']),
        'excluded_count': len(excluded),
        'excluded_pairs': excluded,
        'pairs': report['pairs'],
    }


@router.get('/{experiment_id}/conclusions')
def conclusions(experiment_id: int, db: Session = Depends(connection), actor: User = Depends(current)):
    require_experiment(db, experiment_id)
    items = db.scalars(select(ExperimentConclusion)
                       .where(ExperimentConclusion.experiment_id == experiment_id)
                       .order_by(ExperimentConclusion.version.desc()).limit(100))
    return [views.conclusion(item) for item in items]
