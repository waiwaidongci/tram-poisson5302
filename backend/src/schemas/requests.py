from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from src.constants.enums import Review

class Request(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

class Credentials(Request):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

class Upload(Request):
    name: str = Field(min_length=1, max_length=120)
    filename: str = Field(min_length=1, max_length=160)
    csv_text: str = Field(min_length=1, max_length=2_000_000)

class RunRequest(Request):
    dataset_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=120)
    params: dict = Field(default_factory=dict)

class ReviewRequest(Request):
    review: Review
    note: str = Field(min_length=1, max_length=500)
    decision: str = Field(default='', max_length=120)

class ScheduleRequest(RunRequest):
    recipient: str = Field(min_length=1, max_length=100)
    first_at: datetime
    repeat_daily: bool = False

class ExperimentRequest(Request):
    name: str = Field(min_length=1, max_length=120)
    draw_csv: str = Field(min_length=1, max_length=3_500_000)
    warmup_minutes: int = Field(default=30, ge=0, le=240)
    permutations: int = Field(default=9999, ge=99, le=99999)

class ExperimentReconRequest(Request):
    # 与 headers 中间件 4MB 全局请求体上限保持安全余量
    recon_csv: str = Field(min_length=1, max_length=3_500_000)
    reason: str = Field(default='manual', min_length=1, max_length=80)
