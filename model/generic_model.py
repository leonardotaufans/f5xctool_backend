from pydantic import BaseModel
from sqlmodel import SQLModel, Field


class SchedulerModel(SQLModel, table=True):
    __tablename__ = "tb_snapshot_schedule"
    id: int = Field(primary_key=True)
    scheduled_time: int
    is_started: bool


class SnapRemarksUid(BaseModel):
    uid: str
    environment: str
    lb_type: str
    remarks: str



class SnapshotRemarksUpdate(BaseModel):
    lb_type: str | None
    app_name: str | None
    version: int | None
    environment: str | None
    remarks: str | None
