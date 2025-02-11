import base64
import os
import time
from datetime import timedelta, timezone, datetime
from typing import Annotated

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, APIRouter, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt import InvalidTokenError
from passlib.context import CryptContext
from pydantic import ValidationError
from sqlalchemy import Select, update, Insert
from sqlmodel import Session, select
from starlette import status

import dependency
from helper import event_type
from model.http_model import GenericResponse
from model.log_stuff_model import EventLogSchema
from model.user_model import UserSchema, TokenData, Token, UserToken, UserPublic, UserPatch, UserPost

load_dotenv()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/mgmt/login')
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

engine = dependency.engine
router = APIRouter(tags=['User Management'])


def get_user(username: str) -> UserSchema:
    """
    Get UserSchema from the Database based on username.
    :param username: Username
    :return: UserSchema, might be empty if not found.
    """
    with(Session(engine) as session):
        stmt: Select = select(UserSchema).where(UserSchema.username == username)
        results = session.exec(stmt).first()
        return results


def verify_password(db, password: str) -> bool:
    """
    Verify if password is valid. Parameters assume the User is already selected.
    :param db: Password stored in UserSchema
    :param password: Password inputted by user
    :return: True/False
    """
    return bcrypt.checkpw(password=password.encode('utf-8'),
                          hashed_password=db.crypt.encode('utf-8'))  # return pwd_context.verify(password, db.crypt)


def get_password_hash(password) -> str:
    """
    Get hashed password
    :param password: Raw password
    :return: Hashed password
    """
    return pwd_context.hash(password)


def authenticate_user(username: str, password: str) -> UserSchema:
    """
    Authenticate the user.
    :param username: Username
    :param password: Password
    :returns: UserSchema table or false if user is invalid
    """
    user = get_user(username)
    if not user:
        return False
    if not verify_password(user, password):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> bytes:
    """
    Create access token from user data and the duration
    :param data: Username, in the format of {"sub": "username"}
    :param expires_delta: Duration in minutes
    :return: Encoded JWT Token
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=120)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, os.getenv("SECRET_KEY"), algorithm=os.getenv("ALGORITHM"))
    return encoded_jwt


@router.post('/mgmt/user/refresh', response_model=Token, description='Refresh the token')
async def refresh_token(token: Annotated[str, Depends(oauth2_scheme)]) -> Token:
    """
    Refresh Token
    :param token: The token to be refreshed. This will be checked if the token is valid.
    :type token: str
    :return: New token
    :except HTTPException: Raised if JWT Token is invalid
    """
    try:
        payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
        print(payload.values())
        token = create_access_token(data={"sub": payload.get("sub")},
                                    expires_delta=timedelta(minutes=120))  # todo: change to 15
        user: UserSchema = await get_current_user(token)
        print(user)
        return Token(access_token=token, token_type="bearer", role=user.role,
                     user=UserToken(username=user.username, full_name=user.full_name, email=user.email))
    except (InvalidTokenError, ValidationError):
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                             detail="Your JWT Token is not valid",
                             headers={"WWW-Authenticate": "Bearer"})


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> UserSchema:
    """
    Validates JWT Token and returns a UserSchema
    :param token: User JWT Token
    :return: UserSchema
    :except HTTPException: Raised if user is no longer logged in, or token is invalid.
    """
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
    """
    Verify if user is administrator, first by calling get_current_user() to receive the UserSchema.
    :param current_user: UserSchema from get_current_user()
    :return: UserSchema
    :except HTTPException: Raised if user is not administrator. Normally unused unless user tried through API.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not enough permissions")
    return current_user


@router.post('/mgmt/login', tags=['Login'], response_model=Token)
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
                                 background_tasks: BackgroundTasks) -> Token:
    """
    Login to receive an access token.
    :param background_tasks:
    :param form_data: Takes a form data of Username and Password
    :type form_data: OAuth2PasswordRequestForm
    :return: JWT Token used to authenticate the user
    :rtype: Token
    :except HTTPException: Raised if username/password is invalid
    """
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        background_tasks.add_task(dependency.log_stuff(
            data=EventLogSchema(event_type='user', timestamp=int(round(time.time())),
                                description=f'{form_data.username} failed to login.')))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password",
                            headers={"WWW-Authenticate": "Bearer"})
    access_token_expires = timedelta(minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")))
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)

    return Token(access_token=access_token, token_type="bearer", role=user.role,
                 user=UserToken(username=user.username, full_name=user.full_name, email=user.email))


@router.post('/mgmt/get-myself', response_model=UserPublic)
def get_myself(token: Annotated[str, Depends(get_current_user)]) -> UserSchema:
    """
    Get Myself. This is used to show details on the current user that was previously discarded on the FE.
    :param token: JWT Token from get_current_user.
    :type token: str
    :return: Current User data
    :rtype: UserSchema
    :except HTTPException: Raised if user is logged out while doing this activity.
    """
    return token


@router.get("/mgmt/users", response_model=list[UserSchema])
def list_users(token: Annotated[str, Depends(verify_administrator)], username: str | None = None):
    """
    List all users stored in the database. This can only be used by administrator to manage all users.
    :param token: User Token
    :type token: str
    :param username: (Optional) Username to be searched. Currently unused as there are only a few users to begin with.
    :type username: str
    :return: List of UserSchema
    :rtype: list[UserSchema]
    """
    with (Session(engine) as session):
        statement: Select = select(UserSchema)
        if username:
            statement = statement.where(UserSchema.username == username)
        results = session.exec(statement).all()
        return results


@router.post("/mgmt/users", status_code=status.HTTP_201_CREATED, response_model=GenericResponse)
def create_user(token: Annotated[str, Depends(verify_administrator)], user_form: UserPost, task: BackgroundTasks):
    """
    Create a new user. Currently without any email validation support.
    :param task:
    :param token: Lock this function only for administrator.
    :param user_form: Form of user that will be created (username, email, password, etc.)
    :return: A generic 201 Created Response
    :raise HTTPException: Raised if username/email already exist.
    """
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
    task.add_task(dependency.log_stuff(
        EventLogSchema(event_type=event_type.USER, timestamp=int(round(time.time())),
                       description=f'User {user_form.username} has been created.')))
    return {"result": "ok"}


# Update user data
@router.patch("/mgmt/users", status_code=status.HTTP_200_OK)
def update_user_data(token: Annotated[str, Depends(get_current_user)], form: UserPatch, task: BackgroundTasks):
    """
    Update the user data. Changing username is not supported.
    :param task:
    :param token: Verify if user are modifying their own data or if user has admin privileges.
    :param form: Data that needs to be patched.
    :return:
    """
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
    task.add_task(dependency.log_stuff(
        EventLogSchema(event_type=event_type.USER, timestamp=int(round(time.time())),
                       description=f'User {form.username} updated their data.')))
    return {}


# Check if token is valid
@router.post('/test/token')
def token_test(token: Annotated[str, Depends(get_current_user)]):
    """
    Test the validity of the token. Used by FE to lock the dashboard, not allowing unauthenticated users to access them.
    Token is also used to get the user's role, further locking admin features from the guests.
    :param token: Get current user.
    :return: User, Full Name, and Role.
    """
    print(token.username)
    return {"user": token.username, "full_name": token.full_name, "role": token.role}


@router.post('/test/auth',
             description='Only used to validate if this token has administrator privileges.')
def administrator_authorization_test(token: Annotated[str, Depends(verify_administrator)]):
    """
    Validates if user is admin. Currently unused.
    :param token: User Token
    :return: User Token
    """
    return {"token": token}
