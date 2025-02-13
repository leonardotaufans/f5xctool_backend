import json
import time
from typing import Annotated

from fastapi import APIRouter, Request, BackgroundTasks, Depends
from sqlmodel import select, Session
from starlette import status

import dependency
from model.generic_model import SchedulerModel
from model.log_stuff_model import EventLogSchema
from model.user_model import UserSchema
from routes.users import get_current_user

router = APIRouter(prefix='/xc/logs', tags=['Event Log Management'])
engine = dependency.engine
delay_in_seconds = 300


def snapshot_scheduler():
    this_time = time.time()
    data: SchedulerModel
    with Session(engine) as session:
        stmt = select(SchedulerModel).where(SchedulerModel.id == 1)
        sched: SchedulerModel = session.exec(stmt).first()
        data = sched
        print(sched.scheduled_time)
        sched.scheduled_time = this_time + delay_in_seconds
        session.commit()
        session.refresh(data)
    print(data.scheduled_time)


@router.get('/', description="Get Revision Tool event logs.", response_model=list[EventLogSchema])
def get_tool_logs(token: Annotated[UserSchema, Depends(get_current_user)]) -> list[EventLogSchema]:
    """
    Get Revision Tool event logs.
    :param token: Lock this endpoint for users only
    :type token: UserSchema
    :return: List of Event Logs
    :rtype: EventLogSchema
    """
    with Session(engine) as session:
        stmt = session.exec(select(EventLogSchema)).all()
    return stmt


@router.post("/audit", status_code=status.HTTP_202_ACCEPTED, tags=['XC Audit Log Webhook', 'Snapshot'])
async def webhook_endpoint(request: Request, background_tasks: BackgroundTasks):
    for each in (await request.body()).decode('utf-8').splitlines():
        print(each)
        json_lines = json.loads(each)
        if 'rpc' in json_lines and json_lines['rpc'] in dependency.list_rpc:
            background_tasks.add_task(snapshot_scheduler)
            return {}
    return {"res": "ok"}
