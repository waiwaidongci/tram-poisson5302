"""配对试验的 SQLAlchemy 持久化网关，把 ORM 细节与服务层规则隔离。"""

from sqlalchemy import select

from src.models.experiment import Experiment, ExperimentConclusion
from src.services.audit import record


class ExperimentGateway:
    def __init__(self, db):
        self.db = db

    def find_experiment_by_draw_checksum(self, checksum):
        return self.db.scalar(select(Experiment).where(Experiment.draw_checksum == checksum)
                              .order_by(Experiment.id.desc()).limit(1))

    def create_experiment(self, **kwargs):
        from src.constants.enums import ExperimentStatus
        item = Experiment(status=ExperimentStatus.DRAFT, included_count=0, **kwargs)
        self.db.add(item)
        self.db.flush()
        return item

    def find_active_conclusion(self, experiment_id):
        from src.constants.enums import ConclusionState
        return self.db.scalar(select(ExperimentConclusion).where(
            ExperimentConclusion.experiment_id == experiment_id,
            ExperimentConclusion.state == ConclusionState.ACTIVE).with_for_update())

    def next_conclusion_version(self, experiment_id):
        latest = self.db.scalar(select(ExperimentConclusion.version).where(
            ExperimentConclusion.experiment_id == experiment_id)
            .order_by(ExperimentConclusion.version.desc()).limit(1))
        return (latest or 0) + 1

    def add_conclusion(self, **kwargs):
        item = ExperimentConclusion(**kwargs)
        self.db.add(item)
        self.db.flush()
        return item

    def audit(self, actor, event, target, **info):
        record(self.db, actor, event, target, **info)
