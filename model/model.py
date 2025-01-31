import os
from typing import Dict

from dotenv import load_dotenv
from pydantic import BaseModel, SecretStr
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

class GenericResponse(BaseModel):
    result: str

class SnapshotValueModel(BaseModel):
    new_prod: int
    new_staging: int
    update_prod: int
    update_staging: int


class SnapshotModel(BaseModel):
    result: str
    value: SnapshotValueModel | None = None


class VersionSchema(SQLModel, table=True):
    __tablename__ = 'tb_version'
    uid: str | None = Field(default=None, primary_key=True)
    app_name: str
    original_app_name: str
    timestamp: int
    environment: str
    current_version: int


class StagingRevisionSchema(SQLModel, table=True):
    __tablename__ = 'tb_staging'
    uid: str = Field(default=None, primary_key=True)
    app_name: str
    original_app_name: str
    generated_by: str
    version: int
    timestamp: int
    lb_resource_version: int
    waf_resource_version: int
    origin_resource_version: int
    lb_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    waf_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    origin_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    bot_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    ddos_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))


class ProductionRevisionSchema(SQLModel, table=True):
    __tablename__ = 'tb_production'
    uid: str = Field(default=None, primary_key=True)
    app_name: str
    original_app_name: str
    generated_by: str
    version: int
    timestamp: int
    lb_resource_version: int
    waf_resource_version: int
    origin_resource_version: int
    lb_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    waf_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    origin_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    bot_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    ddos_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))


class UserLogin(BaseModel):
    username: str
    password: str


class UserToken(BaseModel):
    username: str
    full_name: str
    email: str


class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    user: UserToken


class TokenData(BaseModel):
    username: str | None = None


class UserPatch(SQLModel):
    username: str | None = None
    crypt: str | None = None
    full_name: str | None = None
    organization: str | None = None
    is_active: bool | None = None
    email: str | None = None
    role: str | None = None


class UserPost(BaseModel):
    username: str
    password: str
    full_name: str
    organization: str
    is_active: bool
    email: str
    role: str


class UserPublic(SQLModel):
    username: str
    full_name: str
    organization: str
    is_active: bool
    email: str
    registration_date: int
    registered_by: str
    role: str


class UserSchema(SQLModel, table=True):
    __tablename__ = 'tb_users'
    uid: str | None = Field(default=None, primary_key=True)
    username: str
    crypt: str
    full_name: str
    organization: str
    is_active: bool
    email: str
    registration_date: int
    registered_by: str
    role: str


class ReplacePolicySchema(BaseModel):
    app_name: str
    environment: str
    target_version: int
