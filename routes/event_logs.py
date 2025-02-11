import json
import time

from fastapi import APIRouter, Request, BackgroundTasks
from sqlmodel import select, Session
from starlette import status

import dependency
from model.generic_model import SchedulerModel
from model.log_stuff_model import EventLogSchema

router = APIRouter(prefix='/xc/logs')
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


@router.post('/')
def test_log(background_tasks: BackgroundTasks):
    log: EventLogSchema = EventLogSchema(uid="abcdefgh", event_type="test", timestamp=int(round(time.time())),
                                         description='test log')
    background_tasks.add_task(dependency.log_stuff, log)
    return {}


@router.post("/audit", status_code=status.HTTP_202_ACCEPTED)
async def webhook_endpoint(request: Request, background_tasks: BackgroundTasks):
    for each in (await request.body()).decode('utf-8').splitlines():
        print(each)
        json_lines = json.loads(each)
        if 'rpc' in json_lines and json_lines['rpc'] in dependency.list_rpc:
            background_tasks.add_task(snapshot_scheduler)
            return {}
    # print(await request.body())
    # data = await request.json()  # We need to process it like this because XC is sending application/x-ndjson
    # if 'rpc' in data and data['rpc'] in dependency.list_rpc:
    #     background_tasks.add_task(snapshot_scheduler)
    # print(f"Body: {await request.json()}")
    return {"res": "ok"}
