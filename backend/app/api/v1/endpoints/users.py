from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.user import CurrentUserResponse

router = APIRouter()


@router.get('/me', response_model=CurrentUserResponse)
def me(current_user: User = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse.model_validate(current_user)
