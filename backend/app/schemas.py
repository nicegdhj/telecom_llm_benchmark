from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class ModelCreate(BaseModel):
    name: str
    model_config_key: str = "local_qwen"
    model_name: str
    host: str | None = None
    port: int | None = None
    url: str | None = None
    api_key: str | None = None
    auth_header: str | None = "Authorization-Gateway"
    concurrency: int = 20
    gen_kwargs_json: dict[str, Any] = {}


class ModelUpdate(BaseModel):
    model_config_key: str | None = None
    model_name: str | None = None
    host: str | None = None
    port: int | None = None
    url: str | None = None
    api_key: str | None = None
    auth_header: str | None = None
    concurrency: int | None = None
    gen_kwargs_json: dict[str, Any] | None = None


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    model_config_key: str
    model_name: str
    host: str | None
    port: int | None
    url: str | None
    api_key: str | None
    auth_header: str | None
    concurrency: int
    gen_kwargs_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class JudgeCreate(BaseModel):
    name: str
    judge_config_key: str = "local_judge"  # local_judge | api_judge
    model_name: str
    host: str | None = None
    port: int | None = None
    url: str | None = None
    api_key: str | None = None
    score_model_type: str = "maas"         # maas | bailian（api_judge 时生效）
    concurrency: int = 5
    extra_env_json: dict[str, str] = {}


class JudgeUpdate(BaseModel):
    judge_config_key: str | None = None
    model_name: str | None = None
    host: str | None = None
    port: int | None = None
    url: str | None = None
    api_key: str | None = None
    score_model_type: str | None = None
    concurrency: int | None = None
    extra_env_json: dict[str, str] | None = None


class JudgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    judge_config_key: str
    model_name: str
    host: str | None
    port: int | None
    url: str | None
    api_key: str | None
    score_model_type: str
    concurrency: int
    extra_env_json: dict[str, str]
    created_at: datetime
    updated_at: datetime


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    key: str
    type: str
    suite_name: str
    display_name: str | None
    custom_task_num: int | None
    default_data_rel_path: str | None
    is_llm_judge: bool
    created_at: datetime
    alias: str | None = None
    category: str | None = None
    dataset_count: int = 0


class DatasetVersionCreate(BaseModel):
    tag: str
    is_default: bool = False
    note: str | None = None


class DatasetVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_id: int
    tag: str
    data_path: str
    content_hash: str | None
    is_default: bool
    uploaded_at: datetime
    note: str | None


class BatchCreate(BaseModel):
    name: str
    mode: Literal["infer", "eval", "all"] = "all"
    model_ids: list[int] = Field(..., min_length=1)
    task_ids: list[int] = Field(..., min_length=1)
    task_version_map: dict[int, int] | None = None
    default_eval_version: str = "eval_init"
    default_judge_id: int | None = None
    notes: str | None = None


class CloneBatchIn(BaseModel):
    name: str | None = None  # 留空则自动追加"(重试)"


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int | None
    username: str
    display_name: str | None
    role: str
    is_active: bool


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    mode: str
    default_eval_version: str
    default_judge_id: int | None
    notes: str | None
    created_by: UserBrief | None = None
    last_modified_by: UserBrief | None = None
    created_at: datetime
    updated_at: datetime
    status: str = "pending"  # pending | running | success | failed
    eval_config: dict[str, Any] | None = None


class BatchReportRow(BaseModel):
    model_id: int
    model_name: str
    task_id: int
    task_key: str
    prediction_id: int | None
    evaluation_id: int | None
    accuracy: float | None
    num_samples: int | None
    status: str


class BatchReport(BaseModel):
    batch_id: int
    batch_name: str
    generated_at: datetime
    rows: list[BatchReportRow]


class BatchRerun(BaseModel):
    model_ids: list[int] = Field(..., min_length=1)
    task_ids: list[int] = Field(..., min_length=1)
    what: Literal["infer", "eval", "both"] = "both"
    dataset_version_id: int | None = None


class BatchRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    batch_id: int
    rev_num: int
    change_type: str
    change_summary: str | None
    created_at: datetime
    actor: UserBrief | None = None


class PredictionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    model_id: int
    task_id: int
    dataset_version_id: int | None
    status: str
    output_task_id: str | None
    output_path: str | None
    num_samples: int | None
    duration_sec: float | None
    job_id: int | None
    version_label: str | None
    created_at: datetime
    finished_at: datetime | None
    error_msg: str | None


class EvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    prediction_id: int
    eval_version: str
    judge_id: int | None
    status: str
    accuracy: float | None
    details_path: str | None
    num_samples: int | None
    duration_sec: float | None
    job_id: int | None
    version_label: str | None
    created_at: datetime
    finished_at: datetime | None
    error_msg: str | None


# ── Cell 级 ───────────────────────────────────────────────────────────

class CellHistoryItem(BaseModel):
    job_id: int
    kind: Literal["infer", "eval"]
    status: str
    version_label: str | None
    created_at: str | None
    started_at: str | None
    finished_at: str | None
    error_msg: str | None
    returncode: int | None
    log_path: str | None
    prediction_id: int | None
    evaluation_id: int | None
    accuracy: float | None
    num_samples: int | None
    duration_sec: float | None
    based_on_infer: str | None = None
    source_prediction_id: int | None = None


class CellDetailOut(BaseModel):
    batch_id: int
    model_id: int
    task_id: int
    dataset_version_id: int | None
    current_prediction_id: int | None
    current_evaluation_id: int | None
    history: list[CellHistoryItem]


class CellPointerIn(BaseModel):
    current_prediction_id: int | None = None
    current_evaluation_id: int | None = None


class CellRerunIn(BaseModel):
    what: Literal["infer", "eval", "both"]
    source_prediction_id: int | None = None


# ── 测评分析 ──────────────────────────────────────────────────────────

class EvaluationSearchOut(BaseModel):
    """搜索结果展示用，含关联字段。"""
    id: int
    model_id: int
    model_name: str | None
    task_id: int
    task_key: str | None
    batch_id: int | None
    batch_name: str | None
    version_label: str | None
    status: str
    accuracy: float | None
    num_samples: int | None
    duration_sec: float | None
    eval_version: str
    created_at: datetime
    finished_at: datetime | None


class AnalysisViewIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    evaluation_ids: list[int] = []
    chart_config: dict = {}


class AdhocExportIn(BaseModel):
    """临时导出（不依赖已保存模板）。"""
    evaluation_ids: list[int] = []
    filename: str | None = None


class AnalysisViewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    owner_user_id: int
    evaluation_ids: list[int]
    chart_config: dict
    created_at: datetime
    updated_at: datetime


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: str
    status: str
    batch_id: int | None
    model_id: int | None
    task_id: int | None
    pid: int | None
    returncode: int | None
    produces_prediction_id: int | None
    produces_evaluation_id: int | None
    dependency_job_id: int | None
    log_path: str | None
    created_by: UserBrief | None = None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_msg: str | None
    version_label: str | None = None
    model_name: str | None = None
    task_key: str | None = None

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str | None
    role: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    session_token: str
    expires_at: datetime
    user: UserBrief


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=1)


class UserCreate(BaseModel):
    username: str
    password: str = Field(..., min_length=1)
    role: str
    display_name: str | None = None


class UserUpdate(BaseModel):
    role: str | None = None
    display_name: str | None = None
    is_active: bool | None = None


class ResetPasswordIn(BaseModel):
    new_password: str = Field(..., min_length=1)
