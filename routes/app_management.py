import base64
import os
import time
from typing import Annotated

import requests
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import insert, Select, Sequence
from sqlmodel import Session, select, SQLModel

import dependency
from model.model import StagingRevisionSchema, ProductionRevisionSchema, VersionSchema, SnapshotModel, RevisionSchema
from routes.users import get_current_user, verify_administrator

load_dotenv()
router = APIRouter(tags=['XC Management'])
engine = dependency.engine


def push_to_db(environment: str, new_data, exist_data):
    timestamp = int(round(time.time()))
    if environment == "staging":
        q1 = StagingRevisionSchema
    else:
        q1 = ProductionRevisionSchema
    # todo: update the VersionSchema's lb_version stuff
    if new_data:
        with Session(engine) as session:
            session.exec(statement=insert(q1), params=new_data)
            for each in new_data:
                new_app_name: str = each['app_name'].replace('-staging', '').replace('-production', '')
                ins: VersionSchema = VersionSchema(
                    uid=generate_uid(uid_type='app', app_name=each['app_name'], environment=environment,
                                     timestamp=timestamp),
                    app_name=new_app_name,
                    timestamp=timestamp,
                    original_app_name=each['app_name'],
                    environment=environment,
                    current_version=1
                )
                session.add(ins)
            session.commit()
    if exist_data:
        with Session(engine) as session:
            session.exec(statement=insert(q1), params=exist_data)
            for each in exist_data:
                query = session.exec(
                    select(VersionSchema).where(VersionSchema.app_name == each['app_name']).where(
                        VersionSchema.environment == environment)).first()
                query.current_version = each['version']
                session.commit()


def get_model_dict(models: SQLModel):
    return dict((column.name, getattr(models, column.name)) for column in models.__table__.columns)


def generate_uid(uid_type: str, app_name: str, environment: str, timestamp: int, highest_version: int | None = None,
                 ) -> str:
    if uid_type == "app":
        version = ""
    else:
        version = f"_v{highest_version + 1}"
    pre_uid = f"{uid_type}_{app_name}-{environment}{version}_{timestamp}"
    return base64.b64encode(pre_uid.encode('utf-8')).decode('utf-8')


def _get_xc_data(username: str, namespace: str, environment: str, load_balancer_list: list):
    timestamp = int(round(time.time()))
    each_lb_name = []
    # Get all LB Name from the list
    for each in load_balancer_list['items']:
        app_name: str = each['name']
        match environment:
            case "staging":
                if app_name.endswith('-staging'):
                    each_lb_name.append(app_name)
            case "production":
                if app_name.endswith('-staging') is False:
                    each_lb_name.append(app_name)
    # Get all data in SQL data according to environment
    with Session(engine) as session:
        if environment == "staging":
            q1 = StagingRevisionSchema
        else:
            q1 = ProductionRevisionSchema
        sql = session.exec(select(q1)).all()
    # Get only the names from SQL data
    query_lb_name = []
    for _sql in sql:
        query_lb_name.append(_sql.app_name)
    # Check if LB exists in SQL data
    new_lb, exist_lb = [], []
    for each in each_lb_name:
        name = each.replace('-staging', '').replace('-production', '')
        if name not in query_lb_name:
            new_lb.append(each)
        else:
            exist_lb.append(each)
    # Query XC to get the new data
    new_list = []
    print(exist_lb)
    for new in new_lb:
        app_dict = {}
        get_app_data = _get_app(namespace=namespace, app_name=new)
        app_data = get_app_data["replace_form"]
        app_dict['uid'] = generate_uid(uid_type='rev', app_name=app_data['metadata']['name'], environment=environment,
                                       highest_version=0, timestamp=timestamp)
        app_dict['timestamp'] = timestamp
        app_dict['app_name'] = app_data['metadata']['name']

        app_dict['original_app_name'] = get_app_data['replace_form']['metadata']['name']
        app_dict['generated_by'] = username  # todo: get the username
        app_dict['timestamp'] = timestamp
        app_dict['version'] = 1
        app_dict['lb_resource_version'] = int(app_data['resource_version'])
        # Default values that will later be replaced if they exist
        app_dict['origin_resource_version'] = 0
        app_dict['waf_resource_version'] = 0
        app_dict['lb_config'] = get_app_data
        app_dict['ddos_config'] = {}  # todo:
        app_dict['bot_config'] = {}  # todo:
        # Get Origin Pools from App Data
        origin_pool = []
        # Check if Origin Pool exists
        if 'default_route_pools' in app_data['spec']:
            # Check if it has anything. Just in case.
            if app_data['spec']['default_route_pools']:
                for _pool in app_data['spec']['default_route_pools']:
                    __origin__ = _get_origin_pool(namespace=namespace, origin_pool_name=_pool['pool']['name'])
                    origin_pool.append(__origin__)
                    app_dict['origin_resource_version'] = __origin__['resource_version']
        app_dict['origin_config'] = origin_pool
        # Get Application Firewall from App Data
        firewall = {}
        # If WAF isn't set up, it won't show up on JSON, so we have to check it
        if 'app_firewall' in app_data['spec']:
            firewall = _get_app_firewall(namespace=namespace, firewall_name=app_data['spec']['app_firewall']['name'])
            app_dict['waf_resource_version'] = firewall['resource_version']
        app_dict['waf_config'] = firewall
        __xc_name_no_env__: str = (app_data['metadata']['name']).replace('-staging', '').replace('-production', '')
        app_dict['app_name'] = __xc_name_no_env__
        new_list.append(app_dict)
    exist_list = []
    for exist in exist_lb:
        exist_dict = {}
        get_app_data = _get_app(namespace=namespace, app_name=exist)
        app_data = get_app_data['replace_form']
        exist_dict['lb_resource_version'] = int(get_app_data['resource_version'])
        # Default values that will later be replaced if they exist
        exist_dict['origin_resource_version'] = 0
        exist_dict['waf_resource_version'] = 0
        # Get Origin Pools from App Data
        origin_pool = []
        # Check if Origin Pool exists to prevent errors
        if 'default_route_pools' in app_data['spec']:
            # Check if it has anything. Just in case.
            if app_data['spec']['default_route_pools']:
                for _pool in app_data['spec']['default_route_pools']:
                    __origin__ = _get_origin_pool(namespace=namespace, origin_pool_name=_pool['pool']['name'])
                    origin_pool.append(__origin__)
        # Get Application Firewall from App Data
        firewall = {}
        # If WAF isn't set up, it won't show up on JSON, so we have to check it
        if 'app_firewall' in app_data['spec']:
            firewall = _get_app_firewall(namespace=namespace, firewall_name=app_data['spec']['app_firewall']['name'])
        __xc_app_name_no_env__ = exist.replace("-staging", '').replace("-production", '')
        __xc_environment__ = "production"
        if exist.endswith('-staging'):
            __xc_environment__ = "staging"

        # Get current version from app
        with Session(engine) as session:
            get_version_schema = session.exec(
                select(VersionSchema).where(VersionSchema.app_name == __xc_app_name_no_env__).where(
                    VersionSchema.environment == environment)).first()
            print(f"tb_ver: {get_version_schema}")
            # Get configuration from revisions by specific version
            get_revision_schema = session.exec(select(q1).where(q1.app_name == __xc_app_name_no_env__).where(
                q1.version == get_version_schema.current_version)).first()
            print(get_revision_schema)
            if not get_revision_schema:
                print(f"{__xc_app_name_no_env__} missing?")
                continue
        lb_resource_ver = 0
        if get_revision_schema.lb_resource_version:
            lb_resource_ver = get_revision_schema.lb_resource_version
        print(
            f"Current version: {get_version_schema.current_version}, LB resource version: {lb_resource_ver}")
        # with Session(engine) as session:
        #     sel = session.exec(select(q1).where(q1.app_name == __xc_app_name_no_env__)).all()
        # __all_version__ = []
        #
        # for __version__ in sel:
        #     __all_version__.append(__version__.version)
        # highest_version = max(__all_version__)
        # print(f"highest_version: {highest_version}")
        #
        # This is to make SQL data into dict using the version as reference... hopefully.

        # version_list = {get_model_dict(i)['version']: i for i in sel}

        # print(version_list)
        # Check if the config is the latest
        # current_lb_resource_version = version_list[highest_version].lb_config['resource_version']
        # Check if origin pool exists
        # current_origin_list = []
        # if version_list[highest_version].origin_config:
        #     current_origin_list = {i['resource_version']: i for i in version_list[highest_version].origin_config}
        #     exist_dict['origin_resource_version'] = current_origin_list[0]['resource_version']
        # Check if waf_config contains any config
        # current_waf_resource_version = '0'
        # if version_list[highest_version].waf_config:
        #     current_waf_resource_version = version_list[highest_version].waf_config['resource_version']

        # If version mismatched, LB will be updated.
        # lb_update = current_lb_resource_version != get_app_data['resource_version']
        # waf_update = 'resource_version' in firewall and (
        #         int(current_waf_resource_version) < int(firewall['resource_version']))
        # origin_update = current_origin_list == origin_pool
        # Sum the bool to check if any needs to be updated
        # sum_update = lb_update + waf_update + origin_update
        # if sum_update == 0:
        #     continue
        # todo: push to db
        # print(f'update required: {version_list[highest_version].app_name}')
        # if lb_update:
        #     print(f"{version_list[highest_version].app_name} LB requires update")
        #     lb_value = get_app_data
        # else:
        #     lb_value = version_list[highest_version].lb_config
        #
        # if waf_update:
        #     print(f"{version_list[highest_version].app_name} WAF requires update")
        #     waf_value = firewall
        # elif 'resource_version' not in firewall:
        #     waf_value = {}
        # else:
        #     waf_value = version_list[highest_version].waf_config
        #
        # if origin_update:
        #     print(f"{version_list[highest_version].app_name} Origin requires update")
        #     origin_value = origin_pool
        # else:
        #     origin_value = version_list[highest_version].origin_config
        # exist_dict['uid'] = generate_uid(uid_type='rev', app_name=version_list[highest_version].app_name,
        #                                  environment=environment,
        #                                  highest_version=highest_version, timestamp=timestamp)
        #
        # Check if XC has a higher version

        # Check if Load Balancer is the latest
        is_lb_latest_in_xc = get_revision_schema.lb_resource_version < int(get_app_data['resource_version'])
        # Check if App Firewall is the latest
        is_waf_latest_in_xc = False
        if firewall:
            is_waf_latest_in_xc = get_revision_schema.waf_resource_version < int(firewall['resource_version'])
        # Check if Origin Pool is the latest
        is_origin_latest_in_xc = False
        # Check if origin pool is empty first
        if origin_pool:
            if get_revision_schema.origin_config:
                print(origin_pool)
                current_origin_list = {i['resource_version']: i for i in get_revision_schema.origin_config}
                j: int
                if len(origin_pool) > len(current_origin_list):
                    j = len(origin_pool)
                else:
                    j = len(current_origin_list)
                for each in range(j):
                    print(f"current_origin_list: {origin_pool[each]}")
                    if get_revision_schema.origin_config[each]['replace_form']['metadata']['name'] == \
                            origin_pool[each]['replace_form']['metadata'][
                                'name'] and get_revision_schema.origin_config[each]['resource_version'] < \
                            origin_pool[each][
                                'resource_version']:
                        print(
                            f"origin_need_update! {get_revision_schema.origin_config[each]['replace_form']['metadata']['name']} to "
                            f"{origin_pool[each]['resource_version']}")
                        is_origin_latest_in_xc = True
                        continue
                # if origin_pool != current_origin_list:
                #     is_origin_latest_in_xc = True
            else:
                is_origin_latest_in_xc = True
        # These bool are being summed to check if any is True, and if none of them is being updated, they'll be skipped
        print(
            f"app: {__xc_app_name_no_env__}:{environment}, update-lb: {is_lb_latest_in_xc}, update-waf: {is_waf_latest_in_xc}, update_origin: {is_origin_latest_in_xc}")
        sum_update = is_lb_latest_in_xc + is_waf_latest_in_xc + is_origin_latest_in_xc
        if sum_update == 0:
            continue

        # Start changing database from here
        # Update LB
        if is_lb_latest_in_xc:
            print(f"{get_version_schema.app_name} LB requires update")
            lb_value = get_app_data
        # If LB is not updated, the db will copy the old one.
        else:
            lb_value = get_revision_schema.lb_config
        # Update Origin
        if is_origin_latest_in_xc:
            origin_value = origin_pool
        # If Origin is not updated, the db will copy the old one.
        else:
            origin_value = get_revision_schema.origin_config
        # Update WAF
        if is_waf_latest_in_xc:
            waf_value = firewall
            exist_dict['waf_resource_version'] = firewall['resource_version']
        else:
            waf_value = get_revision_schema.waf_config
            exist_dict['waf_resource_version'] = get_revision_schema.waf_config['resource_version']
        exist_dict['uid'] = generate_uid(uid_type='rev', app_name=get_version_schema.app_name,
                                         environment=environment,
                                         highest_version=get_version_schema.current_version, timestamp=timestamp)
        exist_dict['app_name'] = get_version_schema.app_name
        exist_dict['version'] = get_version_schema.current_version + 1
        exist_dict['timestamp'] = timestamp
        exist_dict['original_app_name'] = get_app_data['replace_form']['metadata']['name']
        exist_dict['generated_by'] = username  # todo: update to get the current user
        exist_dict['lb_config'] = lb_value
        exist_dict['waf_config'] = waf_value
        exist_dict['origin_config'] = origin_value
        exist_dict['ddos_config'] = {}
        exist_dict['bot_config'] = {}
        exist_list.append(exist_dict)
    return new_list, exist_list


def _get_app_firewall(namespace: str, firewall_name: str):
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{namespace}/app_firewalls/{firewall_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    query_parameters = {"response_format": "GET_RSP_FORMAT_FOR_REPLACE"}
    req = requests.get(address, headers=headers, params=query_parameters)
    if req.status_code > 200:
        return HTTPException(status_code=req.status_code, detail=req.json())
    return req.json()


def _get_origin_pool(namespace: str, origin_pool_name: str):
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{namespace}/origin_pools/{origin_pool_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    query_parameters = {"response_format": "GET_RSP_FORMAT_FOR_REPLACE"}
    req = requests.get(address, headers=headers, params=query_parameters)
    if req.status_code > 200:
        return HTTPException(status_code=req.status_code, detail=req.json())
    return req.json()


def _get_app(namespace: str, app_name: str):
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{namespace}/http_loadbalancers/{app_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    query_params = {"response_format": "GET_RSP_FORMAT_FOR_REPLACE"}
    req = requests.get(address, params=query_params, headers=headers)
    if req.status_code > 200:
        return HTTPException(req.status_code, req.json())
    return req.json()


# List stored app within database
@router.get('/xc/app', description='List Load Balancers', response_model=list[VersionSchema])
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
@router.get('/xc/app/{app_name}/{environment}', response_model=list[RevisionSchema],
            description='Show full configuration for a specific Load Balancer')
def show_app_details(token: Annotated[str, Depends(get_current_user)], app_name: str, environment: str,
                     ):
    with (Session(engine) as session):
        statement: Select
        if environment == "staging":
            statement = select(StagingRevisionSchema).where(StagingRevisionSchema.app_name == app_name)

        elif environment == "production":
            statement = select(ProductionRevisionSchema).where(ProductionRevisionSchema.app_name == app_name)
        else:
            raise HTTPException(status_code=400, detail="Bad environment syntax. Options: (staging | production)")

        results = session.exec(statement).all()
        return results


@router.post('/xc/snapshot/now', status_code=201, tags=['Manual Snapshot'], response_model=SnapshotModel)
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
    push_to_db(environment="staging", new_data=new_stg, exist_data=exist_stg)
    print(f'new data in stg: {new_stg}\nexist update in stg: {exist_stg}')

    if not new_prd and not new_stg and not exist_prd and not exist_stg:
        return {"result": "No update found."}
    return {"result": "Snapshots created.", "value": {
        "new_prod": len(new_prd),
        "new_staging": len(new_stg),
        "update_prod": len(exist_prd),
        "update_staging": len(exist_stg)
    }}
