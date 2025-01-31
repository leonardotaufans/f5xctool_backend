import base64
import os
import time
from datetime import timedelta, timezone, datetime
from typing import Annotated

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, APIRouter
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt import InvalidTokenError
from passlib.context import CryptContext
from pydantic import ValidationError
from sqlalchemy import Select, update, Insert
from sqlmodel import Session, select
from starlette import status

import dependency
from model.model import UserSchema, TokenData, Token, UserToken, UserPublic, UserPatch, UserPost, GenericResponse

load_dotenv()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/mgmt/login')
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

engine = dependency.engine
router = APIRouter(tags=['User Management'])


def get_user(username: str) -> UserSchema:
    with(Session(engine) as session):
        stmt: Select = select(UserSchema).where(UserSchema.username == username)
        results = session.exec(stmt).first()
        return results


def verify_password(db, password: str):
    return bcrypt.checkpw(password=password.encode('utf-8'),
                          hashed_password=db.crypt.encode('utf-8'))  # return pwd_context.verify(password, db.crypt)


def get_password_hash(password):
    return pwd_context.hash(password)


def authenticate_user(username: str, password: str):
    user = get_user(username)
    if not user:
        return False
    if not verify_password(user, password):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, os.getenv("SECRET_KEY"), algorithm=os.getenv("ALGORITHM"))
    return encoded_jwt


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> UserSchema:
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                          detail="You are no longer logged in",
                                          headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except (InvalidTokenError, ValidationError):
        raise credentials_exception
    user = get_user(token_data.username)
    if user is None:
        raise credentials_exception
    return user


async def verify_administrator(current_user: Annotated[UserSchema, Depends(get_current_user)]):
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not enough permissions")
    return current_user


@router.post('/mgmt/login', tags=['Login'], response_model=Token)
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> Token:
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password",
                            headers={"WWW-Authenticate": "Bearer"})
    access_token_expires = timedelta(minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")))
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
    return Token(access_token=access_token, token_type="bearer", role=user.role,
                 user=UserToken(username=user.username, full_name=user.full_name, email=user.email))


@router.post('/mgmt/get-myself', response_model=UserPublic)
def get_myself(token: Annotated[str, Depends(get_current_user)]):
    return token


@router.get("/mgmt/users", response_model=list[UserSchema])
def list_users(token: Annotated[str, Depends(verify_administrator)], username: str | None = None):
    with (Session(engine) as session):
        statement: Select = select(UserSchema)
        if username:
            statement = statement.where(UserSchema.username == username)
        results = session.exec(statement).all()
        return results


@router.post("/mgmt/users", status_code=status.HTTP_201_CREATED, response_model=GenericResponse)
def create_user(token: Annotated[str, Depends(verify_administrator)], user_form: UserPost):
    # Verify if email and username already exist
    with (Session(engine) as session):
        statement: Select = select(UserSchema)
        user = statement.where(UserSchema.username == user_form.username)
        user_check = session.exec(user).first()
        if user_check:
            return HTTPException(status_code=409, detail="Username already exists")
        mail = statement.where(UserSchema.email == user_form.email)
        email_check = session.exec(mail).first()
        if email_check:
            return HTTPException(status_code=409, detail="Email already exists")
    nx = get_password_hash(password=user_form.password)
    get_time: int = int(round(time.time()))
    uid = base64.urlsafe_b64encode(f"usr_{user_form.username}_{get_time}".encode('utf-8'))
    new_user = UserSchema(uid=uid, username=user_form.username, crypt=nx, full_name=user_form.full_name,
                          organization=user_form.organization,
                          email=user_form.email, registration_date=get_time, registered_by=token.username,
                          role=user_form.role, is_active=user_form.is_active)
    with (Session(engine) as session):
        statement: Insert = select(UserSchema)
        session.exec(statement)
        session.add(new_user)
        session.commit()
    return {"result": "ok"}


# Update user data
@router.patch("/mgmt/users", status_code=status.HTTP_200_OK)
def update_user_data(token: Annotated[str, Depends(get_current_user)], form: UserPatch):
    print(token)
    # Check if user is admin or themselves
    no_auth_except = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                   detail="You are not authorized to make these changes")
    if token.role != "admin":
        if token.username != form.username:
            return no_auth_except
    with Session(engine) as session:
        statement: Select = select(UserSchema).where(UserSchema.username == form.username)
        __user__ = session.exec(statement)
        if not __user__:
            return HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                 detail=f"User {form.username} is not found on the server")
        update_user = form.model_dump(exclude_unset=True)
        if form.crypt:
            update_user['crypt'] = get_password_hash(form.crypt)
        update_query = update(UserSchema).where(UserSchema.username == form.username).values(update_user)
        session.exec(update_query)
        session.commit()
        return {}


# Check if token is valid
@router.post('/test/token')
def token_test(token: Annotated[str, Depends(get_current_user)]):
    print(token.username)
    return {"user": token.username, "full_name": token.full_name, "role": token.role}


@router.post('/test/auth',
             description='Only used to validate if this token has administrator privileges.')
def administrator_authorization_test(token: Annotated[str, Depends(verify_administrator)]):
    return {"token": token}
