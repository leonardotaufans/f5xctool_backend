import os
import time
from typing import Annotated

import requests
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import select, SQLModel, Session
from starlette import status
from starlette.responses import Response

import dependency
from dependency import engine, log_stuff
from helper import event_type, environments, lb_types
from model.cdn_model import CDNLBProductionRevSchema, CDNLBStagingRevSchema
from model.generic_model import SnapRemarksUid
from model.http_model import SnapshotModel, SnapshotContents, SnapshotValueModel, HttpLbProductionRevisionSchema, \
    HttpLbStagingRevisionSchema
from model.log_stuff_model import EventLogSchema
from model.tcp_model import TcpLbProductionRevSchema, TcpLbStagingRevSchema
from model.user_model import UserSchema
from routes.users import verify_administrator

router = APIRouter(prefix='/xc', tags=['Snapshot'])


# Start Snapshot
@router.post('/snapshot/now', status_code=201, response_model=SnapshotModel,
             response_model_exclude_none=True)
def manual_snapshot(token: Annotated[str, Depends(verify_administrator)], response: Response):
    """
    Starts a manual snapshot of all LB.
    :param response: Response if Snapshot didn't find an update.
    :param token: Verify if user is an administrator
    :return: Snapshot model data
    :rtype: SnapshotModel
    """
    # List all HTTP Load Balancer
    dependency.log_stuff(
        EventLogSchema(event_type=event_type.MANUAL_SNAPSHOT, timestamp=int(round(time.time())),
                       description=f'User {token.username} triggered a snapshot.'
                       ))
    http_lb_url = f'{os.getenv("XC_URL")}/api/config/namespaces/{os.getenv("XC_NAMESPACE")}/http_loadbalancers?report_fields=string'
    api_token = os.getenv('XC_APITOKEN')
    headers = {"Authorization": f"APIToken {api_token}", "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}",
               "accept": "application/json", "Access-Control-Allow-Origin": "*"}
    lb_http_req = requests.get(http_lb_url, headers=headers)
    # If APIToken is expired, or accessing the wrong namespace/endpoint
    if lb_http_req.status_code > 200:
        return HTTPException(status_code=lb_http_req.status_code, detail=lb_http_req.json())
    map_lb_http = lb_http_req.json()
    # Get production first
    http_new_prd, http_exist_prd = dependency.get_http_lb_data(username=token.username,
                                                               namespace=os.getenv('XC_NAMESPACE'),
                                                               environment="production",
                                                               load_balancer_list=map_lb_http)
    if dependency.echo: print(f'new data in prod: {http_new_prd}\nexist data: {http_exist_prd}')
    dependency.push_http_lb_to_db(environment="production", new_data=http_new_prd, exist_data=http_exist_prd)
    # Get staging
    http_new_stg, http_exist_stg = dependency.get_http_lb_data(username=token.username,
                                                               namespace=os.getenv('XC_NAMESPACE'),
                                                               environment="staging",
                                                               load_balancer_list=map_lb_http)
    dependency.push_http_lb_to_db(environment="staging", new_data=http_new_stg, exist_data=http_exist_stg)
    if dependency.echo: print(f'new data in stg: {http_new_stg}\nexist update in stg: {http_exist_stg}')
    # TCP LB
    tcp_lb_url = f'{os.getenv("XC_URL")}/api/config/namespaces/{os.getenv("XC_NAMESPACE")}/tcp_loadbalancers?report_fields=string'
    tcp_lb_req = requests.get(url=tcp_lb_url, headers=headers)
    if tcp_lb_req.status_code > 200:
        return HTTPException(status_code=tcp_lb_req.status_code, detail=tcp_lb_req.json())
    map_lb_tcp = tcp_lb_req.json()
    tcp_new_prd, tcp_exist_prd = dependency.get_tcp_lb_data(username=token.username,
                                                            namespace=os.getenv('XC_NAMESPACE'),
                                                            environment="production",
                                                            tcp_lb_list=map_lb_tcp)
    dependency.push_tcp_lb_to_db(environment="production", new_data=tcp_new_prd, exist_data=tcp_exist_prd)
    tcp_new_stg, tcp_exist_stg = dependency.get_tcp_lb_data(username=token.username,
                                                            namespace=os.getenv('XC_NAMESPACE'),
                                                            environment="staging",
                                                            tcp_lb_list=map_lb_tcp)
    dependency.push_tcp_lb_to_db(environment="staging", new_data=tcp_new_stg, exist_data=tcp_exist_stg)

    # Get CDN Load Balancers
    cdn_lb_url = f'{os.getenv("XC_URL")}/api/config/namespaces/{os.getenv("XC_NAMESPACE")}/cdn_loadbalancers?report_fields=string'
    cdn_lb_req = requests.get(cdn_lb_url, headers=headers)
    map_lb_cdn = cdn_lb_req.json()
    cdn_new_prd, cdn_exist_prd = dependency.get_cdn_lb_data(username=token.username,
                                                            namespace=os.getenv('XC_NAMESPACE'),
                                                            environment="production",
                                                            cdn_lb_list=map_lb_cdn)
    cdn_new_stg, cdn_exist_stg = dependency.get_cdn_lb_data(username=token.username,
                                                            namespace=os.getenv('XC_NAMESPACE'),
                                                            environment="staging",
                                                            cdn_lb_list=map_lb_cdn)
    dependency.push_cdn_lb_to_db(environment="production", new_data=cdn_new_prd, exist_data=cdn_exist_prd)
    dependency.push_cdn_lb_to_db(environment="staging", new_data=cdn_new_stg, exist_data=cdn_exist_stg)
    # todo: get healthcheck and service policy push to DB
    # todo: request a remark from the user after a manual snapshot.
    # If all of them are empty
    http_lb_empty = not http_new_prd and not http_new_stg and not http_exist_prd and not http_exist_stg
    tcp_lb_empty = not tcp_new_prd and not tcp_new_stg and not tcp_exist_prd and not tcp_exist_stg
    cdn_lb_empty = not cdn_new_prd and not cdn_new_stg and not cdn_exist_prd and not cdn_exist_stg

    if http_lb_empty and tcp_lb_empty and cdn_lb_empty:
        response.status_code = status.HTTP_204_NO_CONTENT
        return {"result": "No updates found"}

    snapshot_http_new_prd = list_app_and_version(app_list=http_new_prd, lb_type='http')
    snapshot_http_exist_prd = list_app_and_version(http_exist_prd, lb_type='http')
    snapshot_http_new_stg = list_app_and_version(http_new_stg, lb_type='http')
    snapshot_http_exist_stg = list_app_and_version(http_exist_stg, lb_type='http')
    snapshot_model_http = SnapshotValueModel(new_prod=snapshot_http_new_prd, new_staging=snapshot_http_new_stg,
                                             update_prod=snapshot_http_exist_prd,
                                             update_staging=snapshot_http_exist_stg)

    snapshot_tcp_new_prd = list_app_and_version(tcp_new_prd, lb_type='tcp')
    snapshot_tcp_exist_prd = list_app_and_version(tcp_exist_prd, lb_type='tcp')
    snapshot_tcp_new_stg = list_app_and_version(tcp_new_stg, lb_type='tcp')
    snapshot_tcp_exist_stg = list_app_and_version(tcp_exist_stg, lb_type='tcp')
    snapshot_model_tcp = SnapshotValueModel(new_prod=snapshot_tcp_new_prd, new_staging=snapshot_tcp_new_stg,
                                            update_prod=snapshot_tcp_exist_prd,
                                            update_staging=snapshot_tcp_exist_stg)

    snapshot_cdn_new_prd = list_app_and_version(cdn_new_prd, lb_type='cdn')
    snapshot_cdn_exist_prd = list_app_and_version(cdn_exist_prd, lb_type='cdn')
    snapshot_cdn_new_stg = list_app_and_version(cdn_new_stg, lb_type='cdn')
    snapshot_cdn_exist_stg = list_app_and_version(cdn_exist_stg, lb_type='cdn')
    snapshot_model_cdn = SnapshotValueModel(new_prod=snapshot_cdn_new_prd, new_staging=snapshot_cdn_new_stg,
                                            update_prod=snapshot_cdn_exist_prd,
                                            update_staging=snapshot_cdn_exist_stg)

    return SnapshotModel(result="Updates found.",
                         http_lb=snapshot_model_http,
                         tcp_lb=snapshot_model_tcp,
                         cdn_lb=snapshot_model_cdn)


def list_app_and_version(app_list: list, lb_type: str):
    #     name: str
    #     new_version: int
    #     previous_version: int = 0
    if lb_type == "tcp":
        lb_name = "tcp_lb_name"
    elif lb_type == "cdn":
        lb_name = "cdn_lb_name"
    else:
        lb_name = "app_name"
    apps: list[SnapshotContents] = []
    for each in app_list:
        apps.append(SnapshotContents(name=each[lb_name], new_version=each['version'],
                                     previous_version=each['previous_version']))
    return apps


@router.put('/snapshot/remarks')
def snapshot_remarks_by_uid(query: SnapRemarksUid, token: Annotated[UserSchema, Depends(verify_administrator)]):
    uid: str = ''
    name, environment, lb_type = '', '', ''
    q2: any = SQLModel()
    uid = query.uid
    environment = query.environment
    if query.lb_type not in lb_types.types:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid LB Types')
    match query.lb_type:
        case lb_types.http:
            if environment == environments.production:
                q2 = HttpLbProductionRevisionSchema
            else:
                q2 = HttpLbStagingRevisionSchema
        case lb_types.tcp:
            if environment == environments.production:
                q2 = TcpLbProductionRevSchema
            else:
                q2 = TcpLbStagingRevSchema
        case lb_types.cdn:
            if environment == environments.production:
                q2 = CDNLBProductionRevSchema
            else:
                q2 = CDNLBStagingRevSchema
    stmt_uid = select(q2).where(q2.uid == uid)
    with Session(engine) as session:
        act = session.exec(stmt_uid).first()
        act.remarks = query.remarks
        session.commit()
        session.refresh(act)
    log_stuff(EventLogSchema(event_type=event_type.SNAPSHOT, timestamp=int(round(time.time())),
                             description=f"{token.username} updated the snapshot remarks: {act}"))
    return {}
