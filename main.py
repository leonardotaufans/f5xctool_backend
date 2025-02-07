import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import metadata
from routes.cdn_lb import router as cdn_router
from routes.http_lb import router as app_mgmt_router
from routes.snapshot import router as snapshot_router
from routes.tcp_lb import router as tcp_router
from routes.users import router as user_router

load_dotenv()


def create_app():
    api = FastAPI(openapi_tags=metadata.api_metadata, title='F5 XC Tool API', debug=True)
    # todo: update to allow the correct address
    api.add_middleware(CORSMiddleware, allow_origins=['http://localhost', 'http://localhost:25000'],
                       allow_credentials=True, allow_methods=["*"], allow_headers=['*'])
    return api


app = create_app()
app.include_router(snapshot_router)
app.include_router(user_router)
app.include_router(app_mgmt_router)
app.include_router(tcp_router)
app.include_router(cdn_router)

if __name__ == "__main__":
    uvicorn.run('main:app', host='0.0.0.0')
