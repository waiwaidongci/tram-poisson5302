from enum import StrEnum

class Role(StrEnum):
    ADMIN = 'admin'
    ANALYST = 'analyst'
    VIEWER = 'viewer'

class Status(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETE = 'complete'
    FAILED = 'failed'

class Review(StrEnum):
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    RETURNED = 'returned'

class ExperimentStatus(StrEnum):
    DRAFT = 'draft'              # 已登记抽签单，尚无对账数据
    STALE = 'stale'              # 源数据更新后旧结论撤下，等待重算
    COMPUTED = 'computed'        # 当前结论有效
    FAILED = 'failed'            # 重算失败

class ConclusionState(StrEnum):
    ACTIVE = 'active'            # 当前有效结论
    SUPERSEDED = 'superseded'    # 源数据更新后被撤下的旧结论

class SourceSystem(StrEnum):
    SIGNAL = 'signal'            # 信号系统过车量
    DUTY = 'duty'                # 值班系统阻断事件
