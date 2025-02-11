from typing import Dict

from pydantic import BaseModel
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class GenericResponse(BaseModel):
    result: str


class SnapshotContents(BaseModel):
    name: str
    new_version: int
    previous_version: int | None = None


class SnapshotValueModel(BaseModel):
    new_prod: list[SnapshotContents] | None = None
    new_staging: list[SnapshotContents] | None = None
    update_prod: list[SnapshotContents] | None = None
    update_staging: list[SnapshotContents] | None = None


class SnapshotModel(BaseModel):
    result: str
    http_lb: SnapshotValueModel | None = None
    tcp_lb: SnapshotValueModel | None = None
    cdn_lb: SnapshotValueModel | None = None


class HttpLBVersionSchema(SQLModel, table=True):
    __tablename__ = 'tb_http_lb_version'
    uid: str | None = Field(default=None, primary_key=True)
    app_name: str
    original_app_name: str
    timestamp: int
    environment: str
    current_version: int


class HttpLbRevisionSchema(BaseModel):
    uid: str = Field(default=None, primary_key=True)
    app_name: str
    original_app_name: str
    generated_by: str
    version: int
    previous_version: int | None = None
    timestamp: int
    lb_resource_version: int
    waf_resource_version: int
    origin_resource_version: int
    lb_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    waf_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    origin_config: list[Dict] = Field(default_factory=list[dict], sa_column=Column(JSON))
    bot_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    ddos_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    remarks: str | None = None


class HttpLbStagingRevisionSchema(SQLModel, table=True):
    __tablename__ = 'tb_http_lb_staging'
    uid: str = Field(default=None, primary_key=True)
    app_name: str
    original_app_name: str
    generated_by: str
    version: int
    previous_version: int | None = None
    timestamp: int
    lb_resource_version: int
    waf_resource_version: int
    origin_resource_version: int
    lb_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    waf_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    origin_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    bot_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    ddos_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    remarks: str | None = None


class HttpLbProductionRevisionSchema(SQLModel, table=True):
    __tablename__ = 'tb_http_lb_production'
    uid: str = Field(default=None, primary_key=True)
    app_name: str
    original_app_name: str
    generated_by: str
    version: int
    previous_version: int | None = None
    timestamp: int
    lb_resource_version: int
    waf_resource_version: int
    origin_resource_version: int
    lb_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    waf_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    origin_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    bot_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    ddos_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    remarks: str | None = None


class ReplaceHttpLbPolicySchema(BaseModel):
    app_name: str
    environment: str
    target_version: int
