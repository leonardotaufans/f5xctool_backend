# Create SQL Connection
import base64
import json
import os
import time

import requests
from dotenv import load_dotenv
from fastapi import HTTPException
from sqlalchemy import insert, create_engine
from sqlmodel import Session, select, SQLModel

from helper import event_type
from model.cdn_model import CDNLBStagingRevSchema, CDNLBProductionRevSchema, CDNLBVersionSchema
from model.generic_model import SchedulerModel
from model.http_model import HttpLbStagingRevisionSchema, HttpLbProductionRevisionSchema, HttpLBVersionSchema
from model.log_stuff_model import EventLogSchema
from model.tcp_model import TcpLbStagingRevSchema, TcpLbProductionRevSchema, TcpLbVersionSchema

load_dotenv()
sql_address = (f'mysql+pymysql://{os.getenv("SQL_USERNAME")}:{os.getenv("SQL_PASSWORD")}@'
               f'{os.getenv("SQL_ADDRESS")}:{int(os.getenv("SQL_PORT"))}/{os.getenv("SQL_DATABASE_NAME")}')
echo = os.getenv("DEMO") == "1"
engine = create_engine(sql_address, echo=False)
list_rpc = [
    "ves.io.schema.views.http_loadbalancer",
    "ves.io.schema.views.tcp_loadbalancer",
    "ves.io.schema.views.cdn_loadbalancer"
    "ves.io.schema.app_firewall",
    "ves.io.schema.views.origin_pool",
    "ves.io.schema.views."
    "ves.io.schema.healthcheck"
]


def log_stuff(data: EventLogSchema):
    with Session(engine) as session:
        session.add(data)
        session.commit()


def auto_snapshot_pause(status: bool):
    with Session(engine) as session:
        stmt = select(SchedulerModel).where(SchedulerModel.id == 1)
        schedule: SchedulerModel = session.exec(stmt).first()
        schedule.is_started = status
        session.commit()


def push_http_lb_to_db(environment: str, new_data: list | None = None, exist_data: list | None = None):
    """
    Push the snapshot of HTTP Load Balancers to the Database
    :param environment: Environment of the XC Configuration
    :param new_data: List of new Load Balancers.
    :param exist_data: List of existing Load Balancers that have been updated
    """
    timestamp = int(round(time.time()))
    if environment == "staging":
        q1 = HttpLbStagingRevisionSchema
    else:
        q1 = HttpLbProductionRevisionSchema
    # todo: update the VersionSchema's lb_version stuff
    if new_data:
        with Session(engine) as session:
            session.exec(statement=insert(q1), params=new_data)
            for each in new_data:
                log_stuff(
                    EventLogSchema(event_type=event_type.HTTP_SNAPSHOT, timestamp=int(round(time.time())),
                                   description=f'User {q1.generated_by} '
                                               f'created a new snapshot for a new HTTP Load Balancer '
                                               f'{new_app_name} on environment {environment}.',
                                   target_version=each['version']
                                   ))
                new_app_name: str = each['app_name'].replace('-staging', '').replace('-production', '')
                ins: HttpLBVersionSchema = HttpLBVersionSchema(
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
                    select(HttpLBVersionSchema).where(HttpLBVersionSchema.app_name == each['app_name']).where(
                        HttpLBVersionSchema.environment == environment)).first()
                query.current_version = each['version']
                session.commit()
                log_stuff(
                    EventLogSchema(event_type=event_type.HTTP_SNAPSHOT, timestamp=int(round(time.time())),
                                   description=f'User {q1.generated_by} '
                                               f'created a new snapshot for an existing HTTP Load Balancer '
                                               f'{new_app_name} on environment {environment}.',
                                   previous_version=each['previous_version'],
                                   target_version=each['version']
                                   ))


def push_tcp_lb_to_db(environment: str, new_data: list | None = None, exist_data: list | None = None):
    """
    Push the snapshot of HTTP Load Balancers to the Database
    :param environment: Environment of the XC Configuration
    :param new_data: List of new Load Balancers.
    :param exist_data: List of existing Load Balancers that have been updated
    """
    timestamp = int(round(time.time()))
    if environment == "staging":
        q1 = TcpLbStagingRevSchema
    else:
        q1 = TcpLbProductionRevSchema
    # todo: update the VersionSchema's lb_version stuff
    if new_data:
        with Session(engine) as session:
            # Insert LB to Revision table
            session.exec(statement=insert(q1), params=new_data)
            # Insert LB to Version table
            for each in new_data:
                new_app_name: str = each['tcp_lb_name'].replace('-staging', '').replace('-production', '')
                ins: TcpLbVersionSchema = TcpLbVersionSchema(
                    uid=generate_uid(uid_type='tcp', app_name=each['tcp_lb_name'], environment=environment,
                                     timestamp=timestamp),
                    tcp_lb_name=new_app_name,
                    timestamp=timestamp,
                    original_tcp_lb_name=each['original_tcp_lb_name'],
                    environment=environment,
                    current_version=1
                )
                session.add(ins)
                log_stuff(
                    EventLogSchema(event_type=event_type.TCP_SNAPSHOT, timestamp=int(round(time.time())),
                                   description=f'User {q1.generated_by} '
                                               f'created a new snapshot for a new TCP Load Balancer '
                                               f'{new_app_name} on environment {environment}.',
                                   target_version=each['version']
                                   ))
            session.commit()
    if exist_data:
        with Session(engine) as session:
            # Insert to Revision table
            session.exec(statement=insert(q1), params=exist_data)
            # Update Version table
            for each in exist_data:
                query = session.exec(
                    select(TcpLbVersionSchema).where(TcpLbVersionSchema.tcp_lb_name == each['tcp_lb_name']).where(
                        TcpLbVersionSchema.environment == environment)).first()
                query.current_version = each['version']
                session.commit()
                log_stuff(
                    EventLogSchema(event_type=event_type.TCP_SNAPSHOT, timestamp=int(round(time.time())),
                                   description=f'User {q1.generated_by} '
                                               f'created a new snapshot for an existing TCP Load Balancer '
                                               f'{new_app_name} on environment {environment}.',
                                   previous_version=each['previous_version'],
                                   target_version=each['version']
                                   ))


def push_cdn_lb_to_db(environment: str, new_data: list | None = None, exist_data: list | None = None):
    """
    Push the snapshot of HTTP Load Balancers to the Database
    :param environment: Environment of the XC Configuration
    :param new_data: List of new Load Balancers.
    :param exist_data: List of existing Load Balancers that have been updated
    """
    timestamp = int(round(time.time()))
    if environment == "staging":
        q1 = CDNLBStagingRevSchema
    else:
        q1 = CDNLBProductionRevSchema
    # todo: update the VersionSchema's lb_version stuff
    if new_data:
        with Session(engine) as session:
            # Insert LB to Revision table
            session.exec(statement=insert(q1), params=new_data)
            # Insert LB to Version table
            for each in new_data:
                new_app_name: str = (each['cdn_lb_name']).replace('-staging', '').replace('-production', '')
                print(f"cdn db: {each['cdn_lb_name']} {new_app_name}")
                ins: CDNLBVersionSchema = CDNLBVersionSchema(
                    uid=generate_uid(uid_type='cdn', app_name=each['cdn_lb_name'], environment=environment,
                                     timestamp=timestamp),
                    cdn_lb_name=new_app_name,
                    timestamp=timestamp,
                    original_cdn_lb_name=each['original_cdn_lb_name'],
                    environment=environment,
                    current_version=1)
                session.add(ins)
                log_stuff(
                    EventLogSchema(event_type=event_type.CDN_SNAPSHOT, timestamp=int(round(time.time())),
                                   description=f'User {q1.generated_by} '
                                               f'created a new snapshot for a new CDN Load Balancer '
                                               f'{new_app_name} on environment {environment}.',
                                   target_version=each['version']
                                   ))
            session.commit()
    if exist_data:
        with Session(engine) as session:
            # Insert to Revision table
            session.exec(statement=insert(q1), params=exist_data)
            # Update Version table
            for each in exist_data:
                query = session.exec(
                    select(CDNLBVersionSchema).where(CDNLBVersionSchema.cdn_lb_name == each['cdn_lb_name']).where(
                        CDNLBVersionSchema.environment == environment)).first()
                query.current_version = each['version']
                session.commit()
                log_stuff(
                    EventLogSchema(event_type=event_type.CDN_SNAPSHOT, timestamp=int(round(time.time())),
                                   description=f'User {q1.generated_by} '
                                               f'created a new snapshot for an existing CDN Load Balancer '
                                               f'{new_app_name} on environment {environment}.',
                                   previous_version=each['previous_version'],
                                   target_version=each['version']
                                   ))


def get_model_dict(models: SQLModel):
    return dict((column.name, getattr(models, column.name)) for column in models.__table__.columns)


def generate_uid(uid_type: str, app_name: str, environment: str, timestamp: int, highest_version: int = 0,
                 ) -> str:
    """
    Generates the UID using this format:
    <uid_type>_<app_name>-<environment>_<version (optional)_<timestamp>
    :param uid_type: UID Type (app, rev, etc.)
    :param app_name: App name without the environment.
    :param environment: Environment of the app.
    :param timestamp: Current timestamp.
    :param highest_version: The highest version, so the database will write the highest version.
    :return: Base64 of the UID data
    """
    if uid_type == "app":
        version = ""
    else:
        version = f"_v{highest_version + 1}"
    pre_uid = f"{uid_type}_{app_name}-{environment}{version}_{timestamp}"
    return base64.b64encode(pre_uid.encode('utf-8')).decode('utf-8')


def get_http_lb_data(namespace: str, environment: str, load_balancer_list: list, username: str = "autogenerated"):
    """
    Gets the HTTP LB data from XC to be stored to the database.
    :param username: Username of the requester. Defaults to autogenerated.
    :param namespace: Namespace of the XC
    :param environment: Environment of the HTTP Load Balancer
    :param load_balancer_list: List of HTTP Load Balancers name to retrieve from XC.
    :return: List of new HTTP LB and list of existing HTTP LB to be updated.
    """
    timestamp = int(round(time.time()))
    each_lb_name_xc = []
    # Get all LB Name from the list
    for each in load_balancer_list['items']:
        app_name: str = each['name']
        match environment:
            case "staging":
                if app_name.endswith('-staging'):
                    each_lb_name_xc.append(app_name)
            case "production":
                if app_name.endswith('-staging') is False:
                    each_lb_name_xc.append(app_name)
    # Get all data in SQL data according to environment
    with Session(engine) as session:
        if environment == "staging":
            q1 = HttpLbStagingRevisionSchema
        else:
            q1 = HttpLbProductionRevisionSchema
        sql = session.exec(select(q1).order_by(q1.version.desc())).all()
    # Get only the names from SQL data
    query_lb_name = []
    if sql:
        for _sql in sql:
            query_lb_name.append(_sql.app_name)
    # Check if LB exists in SQL data
    new_lb, exist_lb = [], []
    for each in each_lb_name_xc:
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
        get_app_data = _get_http_lb(namespace=namespace, app_name=new)
        app_data = get_app_data["replace_form"]
        app_dict['uid'] = generate_uid(uid_type='rev', app_name=app_data['metadata']['name'], environment=environment,
                                       highest_version=0, timestamp=timestamp)
        app_dict['timestamp'] = timestamp
        app_dict['app_name'] = app_data['metadata']['name']
        app_dict['original_app_name'] = get_app_data['replace_form']['metadata']['name']
        app_dict['generated_by'] = username  # todo: get the username
        app_dict['timestamp'] = timestamp
        app_dict['version'] = 1
        # todo: add previous version
        app_dict['lb_resource_version'] = int(get_app_data['resource_version'])
        # Default values that will later be replaced if they exist
        app_dict['origin_resource_version'] = 0
        app_dict['waf_resource_version'] = 0
        app_dict['lb_config'] = get_app_data
        app_dict['ddos_config'] = {}  # todo:
        app_dict['bot_config'] = {}  # todo:
        app_dict['remarks'] = "System-generated"
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
            firewall = get_app_firewall(namespace=namespace, firewall_name=app_data['spec']['app_firewall']['name'])
            app_dict['waf_resource_version'] = firewall['resource_version']
        app_dict['waf_config'] = firewall
        __xc_name_no_env__: str = (app_data['metadata']['name']).replace('-staging', '').replace('-production', '')
        app_dict['app_name'] = __xc_name_no_env__
        new_list.append(app_dict)
    exist_list = []
    for exist in exist_lb:
        exist_dict = {}
        get_app_data = _get_http_lb(namespace=namespace, app_name=exist)
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
            firewall = get_app_firewall(namespace=namespace, firewall_name=app_data['spec']['app_firewall']['name'])
        __xc_app_name_no_env__ = exist.replace("-staging", '').replace("-production", '')
        __xc_environment__ = "production"
        if exist.endswith('-staging'):
            __xc_environment__ = "staging"

        # Get current version from app
        with Session(engine) as session:
            get_version_schema = session.exec(
                select(HttpLBVersionSchema).where(HttpLBVersionSchema.app_name == __xc_app_name_no_env__).where(
                    HttpLBVersionSchema.environment == environment)).first()
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
            if 'resource_version' in get_revision_schema.waf_config:
                exist_dict['waf_resource_version'] = get_revision_schema.waf_config['resource_version']
            else:
                exist_dict['waf_resource_version'] = 0
            # exist_dict['waf_resource_version'] = get_revision_schema.waf_config['resource_version']
        with Session(engine) as session:
            stmt = select(q1).where(
                q1.app_name == __xc_app_name_no_env__).order_by(q1.version.desc())
            get_ver = session.exec(stmt).first()
            print(f"{__xc_app_name_no_env__} highest version: {get_ver.version}")
            if not get_ver:
                print("Get_ver missing???")

        exist_dict['uid'] = generate_uid(uid_type='rev', app_name=get_version_schema.app_name,
                                         environment=environment,
                                         highest_version=get_version_schema.current_version, timestamp=timestamp)
        exist_dict['app_name'] = get_version_schema.app_name
        exist_dict['version'] = get_ver.version + 1
        exist_dict['timestamp'] = timestamp
        exist_dict['previous_version'] = get_version_schema.current_version
        exist_dict['original_app_name'] = get_app_data['replace_form']['metadata']['name']
        exist_dict['generated_by'] = username  # todo: update to get the current user
        exist_dict['lb_config'] = lb_value
        exist_dict['waf_config'] = waf_value
        exist_dict['origin_config'] = origin_value
        exist_dict['ddos_config'] = {}
        exist_dict['bot_config'] = {}
        exist_list.append(exist_dict)
    # todo: add previous version
    return new_list, exist_list


def get_tcp_lb_data(namespace: str, environment: str, tcp_lb_list: list, username: str = "autogenerated"):
    """
        Gets the TCP LB data from XC to be stored to the database.
        :param username: Username of the requester. Defaults to autogenerated.
        :param namespace: Namespace of the XC
        :param environment: Environment of the HTTP Load Balancer
        :param tcp_lb_list: List of HTTP Load Balancers name to retrieve from XC.
        :return: List of new HTTP LB and list of existing HTTP LB to be updated.
        """
    timestamp = int(round(time.time()))
    each_lb_name_xc = []
    # Get all LB Name from the list
    for each in tcp_lb_list['items']:
        app_name: str = each['name']
        match environment:
            case "staging":
                if app_name.endswith('-staging'):
                    each_lb_name_xc.append(app_name)
            case "production":
                if app_name.endswith('-staging') is False:
                    each_lb_name_xc.append(app_name)
    # Get all data in SQL data according to environment
    with Session(engine) as session:
        if environment == "staging":
            q1 = TcpLbStagingRevSchema
        else:
            q1 = TcpLbProductionRevSchema
        sql = session.exec(select(q1).order_by(q1.version.desc())).all()
    # Get only the names from SQL data
    query_lb_name = []
    if sql:
        for _sql in sql:
            query_lb_name.append(_sql.tcp_lb_name)
    # Check if LB exists in SQL data
    new_lb, exist_lb = [], []
    for each in each_lb_name_xc:
        name = each.replace('-staging', '').replace('-production', '')
        if name not in query_lb_name:
            new_lb.append(each)
        else:
            exist_lb.append(each)
        # Query XC to get the new data
    new_list = []
    if new_lb:
        for new in new_lb:
            app_dict = {}
            print(f"tcp lb app name to get: {new}")
            get_app_data = _get_tcp_lb(namespace=namespace, app_name=new)
            app_data = get_app_data["replace_form"]
            print(f"{new} data: {app_data}")
            app_dict['uid'] = generate_uid(uid_type='rev', app_name=app_data['metadata']['name'],
                                           environment=environment,
                                           highest_version=0, timestamp=timestamp)
            app_dict['timestamp'] = timestamp
            app_dict['original_tcp_lb_name'] = get_app_data['replace_form']['metadata']['name']
            app_dict['generated_by'] = username  # todo: get the username
            app_dict['timestamp'] = timestamp
            app_dict['version'] = 1
            app_dict['lb_resource_version'] = int(get_app_data['resource_version'])
            app_dict['lb_config'] = get_app_data
            # Get Origin Pools from App Data
            origin_pool = []
            # Check if Origin Pool exists
            if 'origin_pools_weights' in app_data['spec']:
                # Check if it has anything. Just in case.
                if app_data['spec']['origin_pools_weights']:
                    for _pool in app_data['spec']['origin_pools_weights']:
                        __origin__ = _get_origin_pool(namespace=namespace, origin_pool_name=_pool['pool']['name'])
                        origin_pool.append(__origin__)
            app_dict['origin_config'] = origin_pool
            __xc_name_no_env__: str = ((app_data['metadata']['name'])
                                       .replace('-staging', '').replace('-production', ''))
            app_dict['tcp_lb_name'] = __xc_name_no_env__
            app_dict['remarks'] = "System-generated"
            new_list.append(app_dict)
    exist_list = []
    if exist_lb:
        for exist in exist_lb:
            exist_dict = {}
            get_app_data = _get_tcp_lb(namespace=namespace, app_name=exist)
            app_data = get_app_data['replace_form']
            exist_dict['lb_resource_version'] = int(get_app_data['resource_version'])
            # Default values that will later be replaced if they exist
            # Get Origin Pools from App Data
            origin_pool = []
            # Check if Origin Pool exists to prevent errors
            if 'origin_pools_weights' in app_data['spec']:
                # Check if it has anything. Just in case.
                if app_data['spec']['origin_pools_weights']:
                    for _pool in app_data['spec']['origin_pools_weights']:
                        __origin__ = _get_origin_pool(namespace=namespace, origin_pool_name=_pool['pool']['name'])
                        origin_pool.append(__origin__)
            __xc_app_name_no_env__ = exist.replace("-staging", '').replace("-production", '')
            __xc_environment__ = "production"
            if exist.endswith('-staging'):
                __xc_environment__ = "staging"

            # Get current version from app
            with Session(engine) as session:
                get_version_schema = session.exec(
                    select(TcpLbVersionSchema).where(
                        TcpLbVersionSchema.tcp_lb_name == __xc_app_name_no_env__).where(
                        TcpLbVersionSchema.environment == environment)).first()
                print(f"tb_ver: {get_version_schema}")
                # Get configuration from revisions by specific version
                get_revision_schema = session.exec(select(q1).where(q1.tcp_lb_name == __xc_app_name_no_env__).where(
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
            is_lb_latest_in_xc = get_revision_schema.lb_resource_version < int(get_app_data['resource_version'])
            # Check if App Firewall is the latest
            is_waf_latest_in_xc = False
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
            # Get the highest version number
            with Session(engine) as session:
                stmt = select(q1).where(
                    q1.tcp_lb_name == __xc_app_name_no_env__).order_by(q1.version.desc())
                get_ver = session.exec(stmt).first()
                print(f"{__xc_app_name_no_env__} highest version: {get_ver.version}")
                if not get_ver:
                    print("Get_ver missing???")

            exist_dict['uid'] = generate_uid(uid_type='rev', app_name=get_version_schema.tcp_lb_name,
                                             environment=environment,
                                             highest_version=get_version_schema.current_version,
                                             timestamp=timestamp)
            exist_dict['tcp_lb_name'] = get_version_schema.tcp_lb_name
            exist_dict['version'] = get_ver.version + 1
            exist_dict['previous_version'] = get_version_schema
            exist_dict['timestamp'] = timestamp
            exist_dict['original_tcp_lb_name'] = get_app_data['replace_form']['metadata']['name']
            exist_dict['generated_by'] = username  # todo: update to get the current user
            exist_dict['lb_config'] = lb_value
            exist_dict['origin_config'] = origin_value
            exist_dict['remarks'] = "System-generated"
            exist_list.append(exist_dict)
    return new_list, exist_list


def get_cdn_lb_data(namespace: str, environment: str, cdn_lb_list: list, username: str = "autogenerated"):
    """
        Gets the CDN LB data from XC to be stored to the database.
        :param username: Username of the requester. Defaults to autogenerated.
        :param namespace: Namespace of the XC
        :param environment: Environment of the HTTP Load Balancer
        :param cdn_lb_list: List of HTTP Load Balancers name to retrieve from XC.
        :return: List of new HTTP LB and list of existing HTTP LB to be updated.
        todo: CDN doesn't have a separate Origin Pool. Erase when able
        todo: Health check should also be stored somewhere.
        """
    timestamp = int(round(time.time()))
    each_lb_name_xc = []
    # Get all LB Name from the list
    for each in cdn_lb_list['items']:
        app_name: str = each['name']
        match environment:
            case "staging":
                if app_name.endswith('-staging'):
                    each_lb_name_xc.append(app_name)
            case "production":
                if app_name.endswith('-staging') is False:
                    each_lb_name_xc.append(app_name)
    # Get all data in SQL data according to environment
    with Session(engine) as session:
        if environment == "staging":
            q1 = CDNLBStagingRevSchema
        else:
            q1 = CDNLBProductionRevSchema
        sql = session.exec(select(q1).order_by(q1.version.desc())).all()
    # Get only the names from SQL data
    query_lb_name = []
    if sql:
        for _sql in sql:
            query_lb_name.append(_sql.cdn_lb_name)
    # Check if LB exists in SQL data
    new_lb, exist_lb = [], []
    for each in each_lb_name_xc:
        name = each.replace('-staging', '').replace('-production', '')
        if name not in query_lb_name:
            new_lb.append(each)
        else:
            exist_lb.append(each)
    # Query XC to get the new data
    new_list = []
    if new_lb:
        for new in new_lb:
            app_dict = {}
            get_app_data = _get_cdn_lb(namespace=namespace, app_name=new)
            app_data = get_app_data["replace_form"]
            __xc_name_no_env__: str = (app_data['metadata']['name']).replace('-staging', '').replace('-production', '')
            print(f"cdn xc name: {__xc_name_no_env__}")
            app_dict['uid'] = generate_uid(uid_type='rev', app_name=__xc_name_no_env__,
                                           environment=environment,
                                           highest_version=0, timestamp=timestamp)
            app_dict['timestamp'] = timestamp
            app_dict['cdn_lb_name'] = __xc_name_no_env__
            app_dict['original_cdn_lb_name'] = app_data['metadata']['name']
            app_dict['generated_by'] = username  # todo: get the username
            app_dict['timestamp'] = timestamp
            app_dict['version'] = 1
            app_dict['lb_resource_version'] = int(get_app_data['resource_version'])
            # Default values that will later be replaced if they exist

            app_dict['lb_config'] = get_app_data
            # Get Origin Pools from App Data
            origin_pool = []
            # Check if Origin Pool exists
            if 'default_route_pools' in app_data['spec']:
                # Check if it has anything. Just in case.
                if app_data['spec']['default_route_pools']:
                    for _pool in app_data['spec']['default_route_pools']:
                        __origin__ = _get_origin_pool(namespace=namespace,
                                                      origin_pool_name=_pool['pool']['name'])
                        origin_pool.append(__origin__)
                        app_dict['origin_resource_version'] = __origin__['resource_version']
            app_dict['origin_config'] = origin_pool
            __xc_name_no_env__: str = ((app_data['metadata']['name'])
                                       .replace('-staging', '').replace('-production', ''))
            app_dict['remarks'] = "System-generated"
            firewall = {}
            # If WAF isn't set up, it won't show up on JSON, so we have to check it
            if 'app_firewall' in app_data['spec']:
                firewall = get_app_firewall(namespace=namespace,
                                            firewall_name=app_data['spec']['app_firewall']['name'])
                app_dict['waf_resource_version'] = firewall['resource_version']
            app_dict['waf_config'] = firewall
            new_list.append(app_dict)
    exist_list = []
    for exist in exist_lb:
        exist_dict = {}
        get_app_data = _get_cdn_lb(namespace=namespace, app_name=exist)
        app_data = get_app_data['replace_form']
        exist_dict['lb_resource_version'] = int(get_app_data['resource_version'])
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
            firewall = get_app_firewall(namespace=namespace,
                                        firewall_name=app_data['spec']['app_firewall']['name'])
        __xc_app_name_no_env__ = exist.replace("-staging", '').replace("-production", '')
        __xc_environment__ = "production"
        if exist.endswith('-staging'):
            __xc_environment__ = "staging"

        # Get current version from app
        with Session(engine) as session:
            get_version_schema = session.exec(
                select(CDNLBVersionSchema).where(CDNLBVersionSchema.cdn_lb_name == __xc_app_name_no_env__).where(
                    CDNLBVersionSchema.environment == environment)).first()
            print(f"tb_ver: {get_version_schema}")
            # Get configuration from revisions by specific version
            get_revision_schema = session.exec(select(q1).where(q1.cdn_lb_name == __xc_app_name_no_env__).where(
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
            print(f"{get_version_schema.cdn_lb_name} LB requires update")
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
        with Session(engine) as session:
            stmt = select(q1).where(
                q1.cdn_lb_name == __xc_app_name_no_env__).order_by(q1.version.desc())
            get_ver = session.exec(stmt).first()
            print(f"{__xc_app_name_no_env__} highest version: {get_ver.version}")
            if not get_ver:
                print("Get_ver missing???")

        exist_dict['uid'] = generate_uid(uid_type='rev', app_name=get_version_schema.cdn_lb_name,
                                         environment=environment,
                                         highest_version=get_version_schema.current_version,
                                         timestamp=timestamp)
        exist_dict['cdn_lb_name'] = get_version_schema.cdn_lb_name
        exist_dict['version'] = get_ver.version + 1
        exist_dict['timestamp'] = timestamp
        exist_dict['previous_version'] = get_version_schema.current_version
        exist_dict['original_cdn_lb_name'] = get_app_data['replace_form']['metadata']['name']
        exist_dict['generated_by'] = username  # todo: update to get the current user
        exist_dict['lb_config'] = lb_value
        exist_dict['waf_config'] = waf_value
        exist_dict['origin_config'] = origin_value
        exist_dict['ddos_config'] = {}
        exist_dict['bot_config'] = {}
        exist_list.append(exist_dict)
    return new_list, exist_list


def get_app_firewall(namespace: str, firewall_name: str):
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


def _get_http_lb(namespace: str, app_name: str):
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{namespace}/http_loadbalancers/{app_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    query_params = {"response_format": "GET_RSP_FORMAT_FOR_REPLACE"}
    req = requests.get(address, params=query_params, headers=headers)
    if req.status_code > 200:
        return HTTPException(req.status_code, req.json())
    return req.json()


def _get_tcp_lb(namespace: str, app_name: str):
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{namespace}/tcp_loadbalancers/{app_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    query_params = {"response_format": "GET_RSP_FORMAT_FOR_REPLACE"}
    req = requests.get(address, params=query_params, headers=headers)
    if req.status_code > 200:
        return HTTPException(req.status_code, req.json())
    return req.json()


def _get_cdn_lb(namespace: str, app_name: str):
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{namespace}/cdn_loadbalancers/{app_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    query_params = {"response_format": "GET_RSP_FORMAT_FOR_REPLACE"}
    req = requests.get(address, params=query_params, headers=headers)
    if req.status_code > 200:
        return HTTPException(req.status_code, req.json())
    return req.json()


def xc_put_http_load_balancers(load_balancer_name: str, configuration):
    """
    Puts (aka REPLACE) HTTP Load Balancers in XC with the one stored on the Database.
    :param load_balancer_name: Name of the HTTP Load Balancer
    :param configuration: Configuration of the HTTP Load Balancer stored on the Database.
    :return: Requests data.
    """
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{os.getenv('XC_NAMESPACE')}/http_loadbalancers/{load_balancer_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    body: str = json.dumps(configuration)
    print(f"jsondump: {body}")
    req = requests.put(url=address, headers=headers, data=body)
    return req


def xc_put_tcp_load_balancers(load_balancer_name: str, configuration):
    """
    Puts (aka REPLACE) TCP Load Balancers in XC with the one stored on the Database.
    :param load_balancer_name: Name of the TCP Load Balancer
    :param configuration: Configuration of the TCP Load Balancer stored on the Database.
    :return: Requests data.
    """
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{os.getenv('XC_NAMESPACE')}/tcp_loadbalancers/{load_balancer_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    body: str = json.dumps(configuration)
    req = requests.put(url=address, headers=headers, data=body)
    return req


def xc_put_cdn_load_balancers(load_balancer_name: str, configuration):
    """
    Puts (aka REPLACE) HTTP Load Balancers in XC with the one stored on the Database.
    :param load_balancer_name: Name of the HTTP Load Balancer
    :param configuration: Configuration of the HTTP Load Balancer stored on the Database.
    :return: Requests data.
    """
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{os.getenv('XC_NAMESPACE')}/cdn_loadbalancers/{load_balancer_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    body: str = json.dumps(configuration)
    req = requests.put(url=address, headers=headers, data=body)
    return req


def xc_put_origin_pools(origin_pools: []):
    """
    Puts (aka REPLACE) ALL Origin Pools in XC with those stored in Database.
    :param origin_pools: Array of all the origin pools that will be replaced.
    :return: Errors if found.
    """
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    errors = []
    for each in origin_pools:
        print(each)
        origin_pool_name = each['metadata']['name']
        address = f"{os.getenv('XC_URL')}/api/config/namespaces/{os.getenv('XC_NAMESPACE')}/origin_pools/{origin_pool_name}"
        body: str = json.dumps(each)
        req = requests.put(url=address, headers=headers, data=body)
        if req.status_code > 200:
            errors.append(f"Error while handling {origin_pool_name}, error: {req.json()}")
    return errors


def put_app_firewall(configuration: dict):
    """
    Puts (aka REPLACE) the App Firewall in XC with the one stored on the Database.
    :param configuration: Configuration in Database.
    :return: Request data
    """
    firewall_name = configuration['metadata']['name']
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{os.getenv('XC_NAMESPACE')}/app_firewalls/{firewall_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    body: str = json.dumps(configuration)
    req = requests.put(url=address, headers=headers, data=body)
    return req


def get_http_load_balancer(load_balancer_name: str):
    """
    Get HTTP Load Balancer from XC.
    :param load_balancer_name: Name of the HTTP Load Balancer
    :return: JSON oof Load Balancer
    """
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{os.getenv('XC_NAMESPACE')}/http_loadbalancers/{load_balancer_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    query_params = {"response_format": "GET_RSP_FORMAT_FOR_REPLACE"}
    req = requests.get(address, params=query_params, headers=headers)
    if req.status_code > 200:
        return HTTPException(req.status_code, req.json())
    return req.json()


def get_tcp_load_balancer(load_balancer_name: str):
    """
    Get TCP Load Balancer from XC.
    :param load_balancer_name: Name of the TCP Load Balancer
    :return: JSON of Load Balancer
    """
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{os.getenv('XC_NAMESPACE')}/tcp_loadbalancers/{load_balancer_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    query_params = {"response_format": "GET_RSP_FORMAT_FOR_REPLACE"}
    req = requests.get(address, params=query_params, headers=headers)
    if req.status_code > 200:
        return HTTPException(req.status_code, req.json())
    return req.json()


def get_cdn_load_balancer(load_balancer_name: str):
    """
    Get HTTP Load Balancer from XC.
    :param load_balancer_name: Name of the HTTP Load Balancer
    :return: JSON oof Load Balancer
    """
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{os.getenv('XC_NAMESPACE')}/cdn_loadbalancers/{load_balancer_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    query_params = {"response_format": "GET_RSP_FORMAT_FOR_REPLACE"}
    req = requests.get(address, params=query_params, headers=headers)
    if req.status_code > 200:
        return HTTPException(req.status_code, req.json())
    return req.json()


def get_all_origin_pools(origin_pool_name: str):
    """
    Get one Origin Pool contained in the Load Balancer. Iterate this for each Origin Pool found in Load Balancers.
    :param origin_pool_name: Name of the origin pool
    :return: JSON of the Origin Pool.
    """
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{os.getenv('XC_NAMESPACE')}/origin_pools/{origin_pool_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    query_parameters = {"response_format": "GET_RSP_FORMAT_FOR_REPLACE"}
    req = requests.get(address, headers=headers, params=query_parameters)
    if req.status_code > 200:
        return HTTPException(status_code=req.status_code, detail=req.json())
    return req.json()


def get_application_firewall(app_firewall_name: str):
    """
    Retrieve App Firewall from XC
    :param app_firewall_name: Name of the App Firewall
    :return: JSON of App Firewall data
    """
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{os.getenv('XC_NAMESPACE')}/app_firewalls/{app_firewall_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    query_parameters = {"response_format": "GET_RSP_FORMAT_FOR_REPLACE"}
    req = requests.get(address, headers=headers, params=query_parameters)
    if req.status_code > 200:
        return HTTPException(status_code=req.status_code, detail=req.json())
    return req.json()
