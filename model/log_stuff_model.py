from sqlmodel import SQLModel, Field


class EventLogSchema(SQLModel, table=True):
    __tablename__ = "tb_events"
    uid: int = Field(default=None, primary_key=True)
    event_type: str
    timestamp: int
    environment: str | None = None
    previous_version: int | None = None
    target_version: int | None = None
    description: str | None = None
