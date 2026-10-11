from typing import Annotated

from fastapi import APIRouter, Depends

from backend.auth.dependencies import get_current_user
from backend.auth.models import User
from backend.auth.rate_limits import check_limit
from backend.model_settings.service import ModelSettingsService

router = APIRouter(prefix="/users/me/models", tags=["model settings"])
Current = Annotated[User, Depends(get_current_user)]


@router.get("")
async def get_models(current: Current):
    return await ModelSettingsService().get()


@router.post("/test-llm")
async def test_llm(current: Current):
    await check_limit("model-test", str(current.id), 20, 3600)
    return await ModelSettingsService().test()
