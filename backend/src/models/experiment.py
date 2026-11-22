from datetime import datetime
from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
from src.constants.enums import ConclusionState, ExperimentStatus
from src.utils.time import now


class Experiment(Base):
    """信号方案配对试验：抽签单登记一次新旧方案的配对比较。"""

    __tablename__ = 'experiments'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    draw_checksum: Mapped[str] = mapped_column(String(64), index=True)
    warmup_minutes: Mapped[int] = mapped_column(default=30)
    permutations: Mapped[int] = mapped_column(default=9999)
    # 已解析的抽签单与最近一次对账记录，作为重算的唯一输入快照
    draw_rows: Mapped[list] = mapped_column(JSON)
    recon_rows: Mapped[list | None] = mapped_column(JSON)
    recon_checksum: Mapped[str | None] = mapped_column(String(64))
    pair_count: Mapped[int] = mapped_column(default=0)
    included_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20), default=ExperimentStatus.DRAFT, index=True)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(500))
    author: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=now)
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)
    computed_at: Mapped[datetime | None]


class ExperimentConclusion(Base):
    """每次重算前撤下的旧结论，保留完整审计轨迹。"""

    __tablename__ = 'experiment_conclusions'
    __table_args__ = (UniqueConstraint('experiment_id', 'version'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey('experiments.id'), index=True)
    version: Mapped[int]
    state: Mapped[str] = mapped_column(String(20), default=ConclusionState.SUPERSEDED, index=True)
    draw_checksum: Mapped[str]
    recon_checksum: Mapped[str]
    result: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(String(300))
    author: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=now)
    superseded_at: Mapped[datetime | None]
