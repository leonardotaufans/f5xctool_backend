from pydantic import BaseModel
from sqlmodel import Field, SQLModel

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