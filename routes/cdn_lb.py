import json
import time
from typing import Annotated

from deepdiff import DeepDiff
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Select
from sqlmodel import Session, select
from starlette import status

import dependency
import metadata
from helper import event_type
from model.cdn_model import CDNLBVersionSchema, CDNLBRevisionSchema, CDNLBStagingRevSchema, CDNLBProductionRevSchema, \
    ReplaceCDNLbPolicySchema
from model.log_stuff_model import EventLogSchema
from routes.users import get_current_user, verify_administrator

load_dotenv()
router = APIRouter(prefix='/xc/cdn-lb', tags=['CDN Load Balancer Management'])
engine = dependency.engine


# List stored app within database
@router.get('/', description='List HTTP Load Balancers', response_model=list[CDNLBVersionSchema])
def list_app(token: Annotated[str, Depends(get_current_user)], name: str | None = None, environment: str | None = None,
             version: int | None = None):
    # print(f'Request token: {token}')
    # print(f'Request:')
    with (Session(engine) as session):
        statement = select(CDNLBVersionSchema).order_by(CDNLBVersionSchema.current_version)
        if name:
            statement = statement.where(CDNLBVersionSchema.cdn_lb_name == name)
        if environment:
            statement = statement.where(CDNLBVersionSchema.environment == environment)
        if version:
            statement = statement.where(CDNLBVersionSchema.version == version)
        results = session.exec(statement).all()

        return results


# List revision data (not decoded) for a specific app and its environments
@router.get('/{app_name}/{environment}', response_model=list[CDNLBRevisionSchema],
            description='Show full configuration for a specific HTTP Load Balancer')
def show_http_lb_details(token: Annotated[str, Depends(get_current_user)], app_name: str, environment: str):
    """
    List all HTTP LB and all of their versions.
    :param token: Verify if user is authenticated
    :param app_name: Name of the HTTP LB
    :param environment: Environment of the app
    :return:
    """
    with (Session(engine) as session):
        statement: Select
        if environment == "staging":
            statement = select(CDNLBStagingRevSchema).where(
                CDNLBStagingRevSchema.cdn_lb_name == app_name).order_by(CDNLBStagingRevSchema.version.desc())
        elif environment == "production":
            statement = select(CDNLBProductionRevSchema).where(
                CDNLBProductionRevSchema.cdn_lb_name == app_name).order_by(CDNLBProductionRevSchema.version.desc())
        else:
            raise HTTPException(status_code=400, detail="Bad environment syntax. Options: (staging | production)")

        results = session.exec(statement).all()
        return results


@router.post('/replace-version', tags=['Replace Version'])
def replace_version(token: Annotated[str, Depends(verify_administrator)],
                    form: ReplaceCDNLbPolicySchema):
    dependency.auto_snapshot_pause(True)
    if form.environment == "staging":
        revision_schema = CDNLBStagingRevSchema
    else:
        revision_schema = CDNLBProductionRevSchema
    with Session(engine) as session:
        ver_schema: CDNLBVersionSchema = session.exec(
            select(CDNLBVersionSchema).where(CDNLBVersionSchema.cdn_lb_name == form.app_name).where(
                CDNLBVersionSchema.environment == form.environment)).first()
        # Verify if the user is requesting to roll back to the same version
        if not ver_schema:
            return HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                 detail='App name, environment, and/or version is not found.')
        if ver_schema.current_version == form.target_version:
            return HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                 detail=f"{form.app_name} on {form.environment} is already running on version {form.target_version}")
    old_version = ver_schema.current_version
    with Session(engine) as session:
        # Get revision schema of the target version
        revision: revision_schema = session.exec(
            select(revision_schema).where(revision_schema.cdn_lb_name == form.app_name).where(
                revision_schema.version == form.target_version)).first()
    # Check if RevisionSchema query came up empty
    if not revision:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                             detail='App name, environment, and/or version is not found.')
    # todo: debug
    target_lb = (revision.lb_config['replace_form'])
    target_origin = []
    # Check if Origin Pools exist
    if revision.origin_config:
        for each in revision.origin_config:
            target_origin.append(each['replace_form'])
    target_waf = {}
    # Check if WAF config exists
    if revision.waf_config:
        if 'replace_form' in revision.waf_config:
            target_waf = (revision.waf_config['replace_form'])

    # Replace config with the stored version

    set_lb = dependency.xc_put_cdn_load_balancers(load_balancer_name=ver_schema.original_cdn_lb_name,
                                                  configuration=target_lb)
    if set_lb.status_code > 200:
        return HTTPException(status_code=set_lb.status_code,
                             detail=f"Error found during pushing Load Balancers. Error: {set_lb.json()}")
    if target_origin:
        set_origin = dependency.xc_put_origin_pools(origin_pools=target_origin)
        if set_origin:
            return HTTPException(status_code=400,
                                 detail=f"Error found during pushing Origin Pools. Errors: {set_origin}")
    if target_waf:
        set_waf = dependency.put_app_firewall(configuration=target_waf)
        if set_waf.status_code > 200:
            return HTTPException(status_code=set_waf.status_code, detail=set_waf.json())

    # Update database with the correct version
    get_lb = dependency.get_cdn_load_balancer(ver_schema.original_cdn_lb_name)
    get_origin = []
    if target_origin:
        for each in target_origin:
            req = dependency.get_all_origin_pools(origin_pool_name=each['metadata']['name'])
            get_origin.append(req)
    get_waf = {}
    if target_waf:
        get_waf = dependency.get_application_firewall(app_firewall_name=target_waf['metadata']['name'])
    with Session(engine) as session:
        revision: revision_schema = session.exec(
            select(revision_schema).where(revision_schema.cdn_lb_name == form.app_name).where(
                revision_schema.version == form.target_version)).first()
        revision.lb_config = get_lb
        revision.waf_config = get_waf
        revision.origin_config = get_origin
        lb_resource_version = 0
        if 'resource_version' in get_lb:
            lb_resource_version = get_lb['resource_version']
        revision.lb_resource_version = lb_resource_version

        waf_resource_version = 0
        if 'resource_version' in get_waf:
            waf_resource_version = get_lb['resource_version']
        revision.waf_resource_version = waf_resource_version
        # Where is origin pool update? It can't be updated here, it has to be individually checked anyway.
        session.commit()
        session.refresh(revision)

    with Session(engine) as session:
        ver_schema: CDNLBVersionSchema = session.exec(
            select(CDNLBVersionSchema).where(CDNLBVersionSchema.cdn_lb_name == form.app_name).where(
                CDNLBVersionSchema.environment == form.environment)).first()
        ver_schema.current_version = form.target_version
        session.commit()
        session.refresh(ver_schema)
    dependency.log_stuff(
        EventLogSchema(event_type=event_type.CDN_REPLACE, timestamp=int(round(time.time())),
                       description=f'User {token.username} '
                                   f'replaced the version of a CDN Load Balancer '
                                   f'{form.app_name} on environment {form.environment}.',
                       target_version=form.target_version,
                       previous_version=old_version,
                       environment=form.environment
                       ))
    dependency.auto_snapshot_pause(False)
    return {}


@router.get('/compare-version', tags=['XC Management'], description=metadata.compare_version_desc)
def compare_cdn_lb_version(right_app_name: str, right_environment: str, right_version: int,
                           left_app_name: str, left_environment: str, left_version: int):
    # Select left revision first
    with Session(engine) as session:
        if left_environment == "staging":
            q1 = CDNLBStagingRevSchema
        else:
            q1 = CDNLBProductionRevSchema
        left_revision_select = select(q1).where(q1.cdn_lb_name == left_app_name).where(q1.version == left_version)
        left_revision = session.exec(left_revision_select).first()
        if not left_revision:
            return HTTPException(status_code=404, detail="Left revision not found.")
    with Session(engine) as session:
        if right_environment == "staging":
            q2 = CDNLBStagingRevSchema
        else:
            q2 = CDNLBProductionRevSchema
        right_revision_select = select(q2).where(q2.cdn_lb_name == right_app_name).where(q2.version == right_version)
        right_revision = session.exec(right_revision_select).first()
        if not right_revision:
            return HTTPException(status_code=404, detail="Right revision not found.")

    root_ddiff = DeepDiff(left_revision, right_revision, ignore_order=True, ignore_string_type_changes=True,
                          verbose_level=0,
                          include_paths=["root['app_name']", "root['original_app_name']"])
    difference = {}
    difference.update({"root_difference": json.loads(root_ddiff.to_json())})
    print(root_ddiff.values())
    lb_ddiff = DeepDiff(left_revision.lb_config["replace_form"], right_revision.lb_config["replace_form"],
                        ignore_order=True)
    difference.update({"lb_difference": json.loads(lb_ddiff.to_json())})

    origin_ddiff = DeepDiff(left_revision.origin_config, right_revision.origin_config,
                            exclude_paths=["[0]['resource_version']"],
                            ignore_order=True)
    difference.update({"origin_difference": json.loads(origin_ddiff.to_json())})
    waf_ddiff = DeepDiff(left_revision.waf_config, right_revision.waf_config,
                         ignore_order=True, include_paths="replace_form")
    difference.update({"waf_difference": json.loads(waf_ddiff.to_json())})
    return difference
