# Create SQL Connection
import json
import os

import requests
from dotenv import load_dotenv
from fastapi import HTTPException
from sqlalchemy import create_engine

load_dotenv()
sql_address = (f'mysql+pymysql://{os.getenv("SQL_USERNAME")}:{os.getenv("SQL_PASSWORD")}@'
               f'{os.getenv("SQL_ADDRESS")}:{int(os.getenv("SQL_PORT"))}/{os.getenv("SQL_DATABASE_NAME")}')  # todo: update to prod

engine = create_engine(sql_address, echo=True)  # todo: Disable echo on prod


def xc_put_http_load_balancers(load_balancer_name: str, configuration):
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{os.getenv('XC_NAMESPACE')}/http_loadbalancers/{load_balancer_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    body: str = json.dumps(configuration)
    print(f"jsondump: {body}")
    req = requests.put(url=address, headers=headers, data=body)
    return req


def xc_put_origin_pools(origin_pools: []):
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
    firewall_name = configuration['metadata']['name']
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{os.getenv('XC_NAMESPACE')}/app_firewalls/{firewall_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    body: str = json.dumps(configuration)
    req = requests.put(url=address, headers=headers, data=body)
    return req


def get_load_balancer(load_balancer_name: str):
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{os.getenv('XC_NAMESPACE')}/http_loadbalancers/{load_balancer_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    query_params = {"response_format": "GET_RSP_FORMAT_FOR_REPLACE"}
    req = requests.get(address, params=query_params, headers=headers)
    if req.status_code > 200:
        return HTTPException(req.status_code, req.json())
    return req.json()


def get_all_origin_pools(origin_pool_name: str):
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
    address = f"{os.getenv('XC_URL')}/api/config/namespaces/{os.getenv('XC_NAMESPACE')}/app_firewalls/{app_firewall_name}"
    headers = {"Authorization": f"APIToken {os.getenv('XC_APITOKEN')}",
               "x-volterra-apigw-tenant": f"{os.getenv('XC_TENANT')}", "accept": "application/json",
               "Access-Control-Allow-Origin": "*"}
    query_parameters = {"response_format": "GET_RSP_FORMAT_FOR_REPLACE"}
    req = requests.get(address, headers=headers, params=query_parameters)
    if req.status_code > 200:
        return HTTPException(status_code=req.status_code, detail=req.json())
    return req.json()