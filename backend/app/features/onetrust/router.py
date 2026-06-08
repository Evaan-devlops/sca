import logging

from fastapi import APIRouter

from app.features.onetrust.auth import login_onetrust
from app.features.onetrust.mapper import DEFAULT_EXPERIENCE_KIT, get_experience_kit_for_url
from app.features.onetrust.schemas import (
    AddAppRequest,
    AddAppResponse,
    LoginResponse,
    MapperDefaultResponse,
    MapperResolveRequest,
    MapperResolveResponse,
)
from app.features.onetrust.websites import add_app_flow

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/auth/login", response_model=LoginResponse)
async def auth_login() -> LoginResponse:
    result = await login_onetrust()
    return LoginResponse(**result)


@router.post("/add_app", response_model=AddAppResponse)
async def add_app(request: AddAppRequest) -> AddAppResponse:
    result = await add_app_flow(url=request.url)
    return AddAppResponse(**result)


@router.get("/mapper/default", response_model=MapperDefaultResponse)
async def mapper_default() -> MapperDefaultResponse:
    return MapperDefaultResponse(
        default_experience_kit=DEFAULT_EXPERIENCE_KIT,
        mode="default_for_all_urls",
    )


@router.post("/mapper/resolve", response_model=MapperResolveResponse)
async def mapper_resolve(request: MapperResolveRequest) -> MapperResolveResponse:
    return MapperResolveResponse(
        url=request.url,
        experience_kit=get_experience_kit_for_url(request.url),
        mode="default_for_all_urls",
    )
