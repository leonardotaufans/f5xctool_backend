from typing import Callable, List

from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute


class log_stuff(APIRoute):
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            req = await request.body()
            print(req)
            response: Response = await original_route_handler(request)
            print(response.body)
            return response

        return custom_route_handler
