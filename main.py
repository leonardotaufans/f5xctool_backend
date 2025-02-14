import asyncio
import os
import time
from contextlib import asynccontextmanager

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from requests import Response
from sqlmodel import Session, select

import dependency
import metadata
import model.user_model
import routes.users
from model.generic_model import SchedulerModel
from routes.cdn_lb import router as cdn_router
from routes.http_lb import router as app_mgmt_router
from routes.snapshot import router as snapshot_router
from routes.tcp_lb import router as tcp_router
from routes.users import router as user_router, get_current_user, verify_administrator
from routes.event_logs import router as websock_router

load_dotenv()


def access_db():
    current: int = int(round(time.time()))
    engine = dependency.engine
    with Session(engine) as session:
        stmt = session.exec(select(SchedulerModel)).first()
        if stmt.scheduled_time == 0:
            return
        if stmt.is_started:
            return
        elif stmt.scheduled_time > current:
            if os.getenv("DEMO") == 1: print(f"Scheduler in {stmt.scheduled_time - current}")
        else:
            stmt.scheduled_time = 0
            session.commit()
            if os.getenv("DEMO") == 1: print("Scheduler reset")
            asyncio.run(auto_snapshot())


async def auto_snapshot():
    # Get token to create a snapshot
    auto_token = await routes.users.login_for_access_token(
        form_data=model.user_model.UserLogin(username="admin", password=os.getenv("AUTOGEN_PASSWORD")))
    if os.getenv("DEMO") == 1: print(auto_token.access_token)
    user = await get_current_user(auto_token.access_token)
    routes.snapshot.manual_snapshot(token=await verify_administrator(user), response=Response())
    if os.getenv("DEMO") == 1: print("manual snapshot completed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler()
    scheduler.add_job(access_db, "interval", seconds=5)
    scheduler.start()
    yield


def create_app():
    api = FastAPI(lifespan=lifespan, openapi_tags=metadata.api_metadata, title='F5 XC Revision Tool API', debug=True,
                  version="0.4")
    # todo: update to allow the correct address
    api.add_middleware(CORSMiddleware, allow_origins=['http://localhost', 'http://localhost:25000'],
                       allow_credentials=True, allow_methods=["*"], allow_headers=['*'])
    return api


my_app = create_app()
my_app.include_router(snapshot_router)
my_app.include_router(user_router)
my_app.include_router(app_mgmt_router)
my_app.include_router(tcp_router)
my_app.include_router(cdn_router)
my_app.include_router(websock_router)

if __name__ == "__main__":
    uvicorn.run('main:my_app', host='0.0.0.0')
