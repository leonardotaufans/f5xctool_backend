from typing import Dict

from pydantic import BaseModel
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class VersionSchema(SQLModel, table=True):
    __tablename__ = 'tb_version'
    uid: str | None = Field(default=None, primary_key=True)
    app_name: str
    timestamp: int
    environment: str
    current_version: int


class StagingRevisionSchema(SQLModel, table=True):
    __tablename__ = 'tb_staging'
    uid: str = Field(default=None, primary_key=True)
    app_name: str
    generated_by: str
    version: int
    timestamp: int
    lb_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    waf_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    origin_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    bot_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    ddos_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))


class ProductionRevisionSchema(SQLModel, table=True):
    __tablename__ = 'tb_production'
    uid: str = Field(default=None, primary_key=True)
    app_name: str
    generated_by: str
    version: int
    timestamp: int
    lb_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    waf_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    origin_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    bot_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    ddos_config: Dict = Field(default_factory=dict, sa_column=Column(JSON))


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


class UserSchema(SQLModel, table=True):
    __tablename__ = 'tb_users'
    uid: str | None = Field(default=None, primary_key=True)
    username: str
    crypt: str
    full_name: str
    organization: str
    email: str
    registration_date: int
    registered_by: str
    role: str
