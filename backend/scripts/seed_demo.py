import json
from sqlalchemy import func, select
from src.config.database import Session
from src.constants.enums import Role
from src.domain.demo import demo_rows
from src.domain.experiment_demo import demo_draw_rows, demo_recon_rows
from src.domain.spec import SPEC
from src.models.experiment import Experiment
from src.models.identity import User
from src.models.source import Dataset
from src.services import experiments as experiment_service
from src.services.datasets import save
from src.services.experiment_gateway import ExperimentGateway
from src.utils.security import hash_password


def seed():
    with Session.begin() as db:
        for role in Role:
            if not db.get(User, role.value):
                db.add(User(username=role.value, role=role, password_hash=hash_password(f'{role.value}-demo-2611')))
        item, created = save(db, SPEC['default_dataset'], SPEC['sample_name'], demo_rows(), 'seed')
        summary = {'users': db.scalar(select(func.count()).select_from(User)),
                   'datasets': db.scalar(select(func.count()).select_from(Dataset)),
                   'seed_dataset_id': item.id, 'row_count': item.row_count, 'checksum': item.checksum,
                   'created_dataset': created}
        summary.update(_seed_experiment(db))
        return summary


def _seed_experiment(db):
    existing = db.scalar(select(Experiment).where(Experiment.name == '信号方案配对试验·首轮抽签').limit(1))
    if existing:
        return {'experiment_id': existing.id, 'experiment_created': False}
    gateway = ExperimentGateway(db)
    experiment, created = experiment_service.register(
        gateway, '信号方案配对试验·首轮抽签', demo_draw_rows(),
        warmup_minutes=30, permutations=9999, actor='seed')
    experiment_service.recompute(gateway, experiment, demo_recon_rows(), 'seed', reason='seed')
    return {'experiment_id': experiment.id, 'experiment_created': created,
            'experiment_included': experiment.included_count}


if __name__ == '__main__':
    print(json.dumps(seed(), ensure_ascii=False))
