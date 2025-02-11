from sqlmodel import SQLModel, Field


class SchedulerModel(SQLModel, table=True):
    __tablename__ = "tb_snapshot_schedule"
    id: int = Field(primary_key=True)
    scheduled_time: int
    is_started: bool