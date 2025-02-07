from typing import Dict

from pydantic import BaseModel
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class CDNLBVersionSchema(SQLModel, table=True):
    __tablename__ = 'tb_cdn_lb_version'
    uid: str | None = Field(default=None, primary_key=True)
    cdn_lb_name: str
    original_cdn_lb_name: str
    timestamp: int
    environment: str
    current_version: int


class CDNLBRevisionSchema(BaseModel):
    uid: str = Field(default=None, primary_key=True)
    cdn_lb_name: str
    original_cdn_lb_name: str
    generated_by: str
    version: int
    previous_version: int | None = None
    timestamp: int
    lb_resource_version: int
    waf_resource_version: int
    lb_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    waf_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    origin_config: list[Dict] = Field(default_factory=list[dict], sa_column=Column(JSON))
    remarks: str | None = None


class CDNLBStagingRevSchema(SQLModel, table=True):
    __tablename__ = 'tb_cdn_lb_staging'
    uid: str = Field(default=None, primary_key=True)
    cdn_lb_name: str
    original_cdn_lb_name: str
    generated_by: str
    version: int
    previous_version: int | None = None
    timestamp: int
    lb_resource_version: int
    waf_resource_version: int
    lb_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    waf_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    origin_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    remarks: str | None = None


class CDNLBProductionRevSchema(SQLModel, table=True):
    __tablename__ = 'tb_cdn_lb_production'
    uid: str = Field(default=None, primary_key=True)
    cdn_lb_name: str
    original_cdn_lb_name: str
    generated_by: str
    version: int
    previous_version: int | None = None
    timestamp: int
    lb_resource_version: int
    waf_resource_version: int
    lb_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    waf_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    origin_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    remarks: str | None = None


class ReplaceCDNLbPolicySchema(BaseModel):
    app_name: str
    environment: str
    target_version: int