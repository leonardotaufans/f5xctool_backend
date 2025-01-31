from typing import Annotated

from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select
from starlette import status

import dependency
from dependency import engine
from model.model import ReplacePolicySchema, StagingRevisionSchema, ProductionRevisionSchema, VersionSchema
from routes.users import verify_administrator

router = APIRouter()


@router.post('/xc/app/replace-version', tags=['Replace Version'])
def replace_version(token: Annotated[str, Depends(verify_administrator)], form: ReplacePolicySchema):  # todo: add security
    if form.environment == "staging":
        revision_schema = StagingRevisionSchema
    else:
        revision_schema = ProductionRevisionSchema
    with Session(engine) as session:
        ver_schema: VersionSchema = session.exec(
            select(VersionSchema).where(VersionSchema.app_name == form.app_name).where(
                VersionSchema.environment == form.environment)).first()
        # Verify if the user is requesting to roll back to the same version
        if not ver_schema:
            return HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                 detail='App name, environment, and/or version is not found.')
        if ver_schema.current_version == form.target_version:
            return HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                 detail=f"{form.app_name} on {form.environment} is already running on version {form.target_version}")
    with Session(engine) as session:
        # Get revision schema of the target version
        revision: revision_schema = session.exec(
            select(revision_schema).where(revision_schema.app_name == form.app_name).where(
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
    set_lb = dependency.xc_put_http_load_balancers(load_balancer_name=ver_schema.original_app_name,
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
    get_lb = dependency.get_load_balancer(ver_schema.original_app_name)
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
            select(revision_schema).where(revision_schema.app_name == form.app_name).where(
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
        ver_schema: VersionSchema = session.exec(
            select(VersionSchema).where(VersionSchema.app_name == form.app_name).where(
                VersionSchema.environment == form.environment)).first()
        ver_schema.current_version = form.target_version
        session.commit()
        session.refresh(ver_schema)
    return {}
