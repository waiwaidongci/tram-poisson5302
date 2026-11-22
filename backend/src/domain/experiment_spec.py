"""信号方案配对试验的字段口径。

抽签单固定每对相邻路口（同组）的两个班次，以及各班次执行旧/新方案的顺序与
切换时点；过车量与阻断事件分别来自信号系统和值班系统，按抽签单跨系统对账。
"""

DRAW_FIELDS = [
    {"key": "pair_id", "label": "配对编号", "type": "string", "required": True, "max_length": 40},
    {"key": "group_name", "label": "相邻路口同组", "type": "string", "required": True, "max_length": 80},
    {"key": "shift_id", "label": "班次编号", "type": "string", "required": True, "max_length": 40},
    {"key": "window_start", "label": "班次开始时间", "type": "datetime", "required": True},
    {"key": "window_end", "label": "班次结束时间", "type": "datetime", "required": True},
    {"key": "scheme_order", "label": "本班方案顺序", "type": "select", "required": True,
     "options": ["旧-新", "新-旧"]},
    {"key": "switch_at", "label": "方案切换时间", "type": "datetime", "required": True},
]

RECON_FIELDS = [
    {"key": "pair_id", "label": "配对编号", "type": "string", "required": True, "max_length": 40},
    {"key": "shift_id", "label": "班次编号", "type": "string", "required": True, "max_length": 40},
    {"key": "source_system", "label": "来源系统", "type": "select", "required": True,
     "options": ["signal", "duty"]},
    {"key": "record_start", "label": "记录开始时间", "type": "datetime", "required": True},
    {"key": "record_end", "label": "记录结束时间", "type": "datetime", "required": True},
    {"key": "exposure", "label": "过车车次", "type": "int", "required": False, "min": 0, "max": 100000},
    {"key": "blockage", "label": "阻断次数", "type": "int", "required": False, "min": 0, "max": 100000},
]

SCHEME_OLD = "旧方案"
SCHEME_NEW = "新方案"
WARMUP_MINUTES_DEFAULT = 30
PERMUTATIONS_DEFAULT = 9999
EXACT_ENUMERATION_LIMIT = 20
MAX_DRAW_ROWS = 2000
MAX_RECON_ROWS = 20000
