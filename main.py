import os
from datetime import datetime, timezone, timedelta
from typing import Annotated

import bcrypt
import jwt
import requests
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt import InvalidTokenError
from passlib.context import CryptContext
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlmodel import Session, select

from model.model import VersionSchema, StagingRevisionSchema, ProductionRevisionSchema, UserSchema, TokenData, Token, \
    UserToken
from xc_helper import _get_xc_data, push_to_db

load_dotenv()


def create_app():
    api = FastAPI()
    # todo: update to allow the correct address
    api.add_middleware(CORSMiddleware, allow_origins=['http://localhost', 'http://localhost:25000'],
                       allow_credentials=True, allow_methods=["*"], allow_headers=['*']
                       # allow_origin_regex='http://localhost:*'
                       )
    # api.add_middleware(log_stuff)
    return api


app = create_app()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/mgmt/login')
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Create SQL Connection
sql_address = (f'mysql://{os.getenv("SQL_USERNAME")}:{os.getenv("SQL_PASSWORD")}@'
               f'{os.getenv("SQL_ADDRESS")}:{int(os.getenv("SQL_PORT"))}/{os.getenv("SQL_DATABASE_NAME")}')  # todo: update to prod

engine = create_engine(sql_address, echo=True)  # todo: Disable echo on prod


def get_user(username: str) -> UserSchema:
    with(Session(engine) as session):
        stmt = select(UserSchema).where(UserSchema.username == username)
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
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not enough permissions",
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


@app.post('/mgmt/login')
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> Token:
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password",
                            headers={"WWW-Authenticate": "Bearer"})
    access_token_expires = timedelta(minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")))
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
    return Token(access_token=access_token, token_type="bearer", role=user.role,
                 user=UserToken(username=user.username, full_name=user.full_name, email=user.email))


# Check if token is valid
@app.post('/test/token')
def token_test(token: Annotated[str, Depends(get_current_user)]):
    print(token.username)
    return {"user": token.username, "full_name": token.full_name, "role": token.role}


@app.post('/test/auth')
def auth_test(token: Annotated[str, Depends(verify_administrator)]):
    return {"token": token}


# List stored app within database
@app.get('/xc/app')
def list_app(token: Annotated[str, Depends(get_current_user)], name: str | None = None, environment: str | None = None,
             version: int | None = None):
    # print(f'Request token: {token}')
    # print(f'Request:')
    with (Session(engine) as session):
        statement = select(VersionSchema)
        if name:
            statement = statement.where(VersionSchema.app_name == name)
        if environment:
            statement = statement.where(VersionSchema.environment == environment)
        if version:
            statement = statement.where(VersionSchema.version == version)
        results = session.exec(statement).all()

        return results


# List revision data (not decoded) for a specific app and its environments
@app.get('/xc/app/{app_name}/{environment}')
def list_app(token: Annotated[str, Depends(get_current_user)], app_name: str, environment: str,
             version: int | None = None):
    with (Session(engine) as session):
        if environment == "staging":
            statement = select(StagingRevisionSchema).where(StagingRevisionSchema.app_name == app_name)

        elif environment == "production":
            statement = select(ProductionRevisionSchema).where(ProductionRevisionSchema.app_name == app_name)
        else:
            raise HTTPException(status_code=400, detail="Bad environment syntax. Options: (staging | production)")

        results = session.exec(statement).all()
        return results


@app.post('/xc/snapshot/now', status_code=201)
def manual_snapshot(token: Annotated[str, Depends(verify_administrator)]):
    print(token.username)
    # List all HTTP Load Balancer
    http_lb_url = f'https://ocbc-bank.console.ves.volterra.io/api/config/namespaces/poc1/http_loadbalancers?report_fields=string'
    apitoken = os.getenv('XC_APITOKEN')
    headers = {"Authorization": f"APIToken {apitoken}", "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}",
               "accept": "application/json", "Access-Control-Allow-Origin": "*"}
    lb_http_req = requests.get(http_lb_url, headers=headers)
    # If APIToken is expired, or accessing the wrong namespace/endpoint
    if lb_http_req.status_code > 200:
        return HTTPException(status_code=lb_http_req.status_code, detail=lb_http_req.json())
    map_lb_http = lb_http_req.json()
    # Get production first
    new_prd, exist_prd = _get_xc_data(username=token.username, namespace=os.getenv('XC_NAMESPACE'),
                                      environment="production",
                                      load_balancer_list=map_lb_http)
    print(f'new data in prod: {new_prd}\nexist data: {exist_prd}')
    push_to_db(environment="production", new_data=new_prd, exist_data=exist_prd)
    # Get staging
    new_stg, exist_stg = _get_xc_data(username=token.username, namespace=os.getenv('XC_NAMESPACE'),
                                      environment="staging",
                                      load_balancer_list=map_lb_http)
    print(f'new data in stg: {new_stg}\nexist update in stg: {exist_stg}')
    if not new_prd and not new_stg and not exist_prd and not exist_stg:
        return {"result": "No update found."}
    return {"result": "Snapshots created.", "value": {
        "new_prod": len(new_prd),
        "new_staging": len(new_stg),
        "update_prd": len(exist_prd),
        "update_stg": len(exist_stg)
    }}


if __name__ == "__main__":
    uvicorn.run('main:app', host='0.0.0.0')
