import base64
import os
import time

import requests
from dotenv import load_dotenv
from fastapi import HTTPException
from sqlalchemy import create_engine, insert, select
from sqlmodel import Session, SQLModel

from model.model import StagingRevisionSchema, ProductionRevisionSchema, VersionSchema

load_dotenv()
# Create SQL Connection
sql_address = (f'mysql://{os.getenv("SQL_USERNAME")}:{os.getenv("SQL_PASSWORD")}@'
               f'{os.getenv("SQL_ADDRESS")}:{int(os.getenv("SQL_PORT"))}/{os.getenv("SQL_DATABASE_NAME")}')  # todo: update to prod

engine = create_engine(sql_address, echo=True)  # todo: Disable echo on prod


def push_to_db(environment: str, new_data, exist_data):
    timestamp = int(round(time.time()))
    if environment == "staging":
        q1 = StagingRevisionSchema
    else:
        q1 = ProductionRevisionSchema
    if new_data:
        with Session(engine) as session:
            session.exec(statement=insert(q1), params=new_data)
            for each in new_data:
                ins: VersionSchema = VersionSchema(
                    uid=generate_uid(uid_type='app', app_name=each['app_name'], environment=environment,
                                     timestamp=timestamp),
                    app_name=each['app_name'],
                    timestamp=timestamp,
                    environment=environment,
                    current_version=1
                )
                session.add(ins)
            session.commit()
    if exist_data:
        with Session(engine) as session:
            session.exec(statement=insert(q1), params=exist_data)
            for each in exist_data:
                query = session.exec(select(VersionSchema).where(VersionSchema.app_name == each['app_name']).where(
                    VersionSchema.environment == environment)).one()
                query.current_version = exist_data['version']
                session.commit()


def get_model_dict(model: SQLModel):
    return dict((column.name, getattr(model, column.name)) for column in model.__table__.columns)


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
    for new in new_lb:
        app_dict = {}
        get_app_data = _get_app(namespace=namespace, app_name=new)
        app_data = get_app_data["replace_form"]
        app_dict['uid'] = generate_uid(uid_type='rev', app_name=app_data['metadata']['name'], environment=environment,
                                       highest_version=0, timestamp=timestamp)
        app_dict['timestamp'] = timestamp
        app_dict['app_name'] = app_data['metadata']['name']
        app_dict['generated_by'] = username  # todo: get the username
        app_dict['timestamp'] = timestamp
        app_dict['version'] = 1
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
        app_dict['origin_config'] = origin_pool
        # Get Application Firewall from App Data
        firewall = {}
        # If WAF isn't set up, it won't show up on JSON, so we have to check it
        if 'app_firewall' in app_data['spec']:
            firewall = _get_app_firewall(namespace=namespace, firewall_name=app_data['spec']['app_firewall']['name'])
        app_dict['waf_config'] = firewall
        new_list.append(app_dict)
    exist_list = []
    for exist in exist_lb:
        exist_dict = {}
        get_app_data = _get_app(namespace=namespace, app_name=exist)
        app_data = get_app_data['replace_form']
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
        with Session(engine) as session:
            sel = session.exec(select(q1).where(q1.app_name == __xc_app_name_no_env__)).all()
        __all_version__ = []
        for __version__ in sel:
            __all_version__.append(__version__.version)
        highest_version = max(__all_version__)
        print(f"highest_version: {highest_version}")
        # This is to make SQL data into dict using the version as reference... hopefully.
        version_list = {get_model_dict(i)['version']: i for i in sel}

        print(version_list)
        # Check if the config is the latest
        current_lb_resource_version = version_list[highest_version].lb_config['resource_version']
        # Check if origin pool exists
        current_origin_list = []
        if version_list[highest_version].origin_config:
            current_origin_list = {i['resource_version']: i for i in version_list[highest_version].origin_config}
        # Check if waf_config contains any config
        current_waf_resource_version = '0'
        if version_list[highest_version].waf_config:
            current_waf_resource_version = version_list[highest_version].waf_config['resource_version']

        # If version mismatched, LB will be updated.
        lb_update = current_lb_resource_version != get_app_data['resource_version']
        waf_update = 'resource_version' in firewall and (
                int(current_waf_resource_version) != int(firewall['resource_version']))
        origin_update = current_origin_list == origin_pool
        # Sum the bool to check if any needs to be updated
        sum_update = lb_update + waf_update + origin_update
        if sum_update == 0:
            continue
        # todo: push to db
        print(f'update required: {version_list[highest_version].app_name}')
        if lb_update:
            print(f"{version_list[highest_version].app_name} LB requires update")
            lb_value = get_app_data
        else:
            lb_value = version_list[highest_version].lb_config

        if waf_update:
            print(f"{version_list[highest_version].app_name} WAF requires update")
            waf_value = firewall
        elif 'resource_version' not in firewall:
            waf_value = {}
        else:
            waf_value = version_list[highest_version].waf_config

        if origin_update:
            print(f"{version_list[highest_version].app_name} Origin requires update")
            origin_value = origin_pool
        else:
            origin_value = version_list[highest_version].origin_config
        exist_dict['uid'] = generate_uid(uid_type='rev', app_name=version_list[highest_version].app_name,
                                         environment=environment,
                                         highest_version=highest_version, timestamp=timestamp)
        exist_dict['app_name'] = version_list[highest_version].app_name
        exist_dict['version'] = highest_version + 1
        exist_dict['timestamp'] = timestamp
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
