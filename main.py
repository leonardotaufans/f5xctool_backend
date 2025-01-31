import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import metadata
from routes.app_management import router as app_mgmt_router
from routes.users import router as user_router
from routes.version_replace import router as version_router

load_dotenv()


def create_app():
    api = FastAPI(openapi_tags=metadata.api_metadata)
    # todo: update to allow the correct address
    api.add_middleware(CORSMiddleware, allow_origins=['http://localhost', 'http://localhost:25000'],
                       allow_credentials=True, allow_methods=["*"], allow_headers=['*'])
    return api


app = create_app()
app.include_router(version_router)
app.include_router(user_router)
app.include_router(app_mgmt_router)

if __name__ == "__main__":
    uvicorn.run('main:app', host='0.0.0.0')
