from fastapi import APIRouter, Query
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
)

from .types import (
    SubscribeBody,
    SubscribeResponse,
    UpdatePackageBody,
    CreatePackageBody,
    CreatePackageResponse,
)
from ..dependencies import get_connection
from ..types import Request
from ...services.constants import Role
from ...services.packages import errors
from ...services.packages.service import PackageService

service = PackageService(get_connection())
router = APIRouter(prefix="/packages", tags=["packages"])


def _require_role(request: Request, *roles: Role) -> None:
    """Raises ``InsufficientRoleError`` if the user lacks the required role."""
    if request.state.user["role"] not in roles:
        raise errors.InsufficientRoleError()


@router.get(
    "",
    summary="Lists all available packages",
    response_description="List of enabled packages",
)
async def list_packages() -> list[dict]:
    """Returns all currently enabled packages."""
    return [dict(row) for row in service.get_available_packages()]


@router.post(
    "",
    summary="Creates a new package",
    response_description="The created package ID",
    tags=["admin"],
    responses={
        HTTP_403_FORBIDDEN: {
            "model": errors.InsufficientRoleError.openapi_model(),
        },
        HTTP_409_CONFLICT: {
            "model": errors.DuplicatePackageNameError.openapi_model(),
        },
    },
)
async def create_package(
    request: Request, body: CreatePackageBody
) -> CreatePackageResponse:
    """Creates a new package in the catalog."""
    _require_role(request, Role.ADMIN)
    return CreatePackageResponse(id=service.create_package(body.name, body.price))


@router.patch(
    "/{package_id}",
    summary="Updates a package",
    tags=["admin"],
    responses={
        HTTP_403_FORBIDDEN: {
            "model": errors.InsufficientRoleError.openapi_model(),
        },
        HTTP_404_NOT_FOUND: {
            "model": errors.PackageNotFoundError.openapi_model(),
        },
        HTTP_409_CONFLICT: {
            "model": errors.DuplicatePackageNameError.openapi_model(),
        },
    },
)
async def update_package(
    request: Request, package_id: int, body: UpdatePackageBody
) -> None:
    """Updates a package's name, price, or enabled status."""
    _require_role(request, Role.ADMIN)
    service.update_package(
        package_id,
        name=body.name,
        price=body.price,
        is_enabled=body.is_enabled,
    )


@router.post(
    "/subscribe",
    summary="Subscribes to a package",
    response_description="The subscription details with Jalali dates",
    responses={
        HTTP_400_BAD_REQUEST: {
            "model": (
                errors.PackageDisabledError.openapi_model()
                | errors.InvalidWeekSelectionError.openapi_model()
            ),
        },
        HTTP_404_NOT_FOUND: {
            "model": errors.PackageNotFoundError.openapi_model(),
        },
        HTTP_409_CONFLICT: {
            "model": errors.ActiveSubscriptionExistsError.openapi_model(),
        },
    },
)
async def subscribe(request: Request, body: SubscribeBody) -> SubscribeResponse:
    """Purchases a new package subscription for the authenticated user."""
    result = service.subscribe(
        user_id=request.state.user["id"],
        package_id=body.package_id,
        meal_type=body.meal_type,
        diet_drink=body.diet_drink,
        allergies=body.allergies,
        num_weeks=body.num_weeks,
    )
    return SubscribeResponse(**result)


@router.post(
    "/reserve",
    summary="Reserves a package for after the current subscription ends",
    response_description="The reserved subscription details with Jalali dates",
    responses={
        HTTP_400_BAD_REQUEST: {
            "model": (
                errors.PackageDisabledError.openapi_model()
                | errors.ActiveSubscriptionNotFoundError.openapi_model()
                | errors.InvalidWeekSelectionError.openapi_model()
            ),
        },
        HTTP_404_NOT_FOUND: {
            "model": errors.PackageNotFoundError.openapi_model(),
        },
        HTTP_409_CONFLICT: {
            "model": errors.ReservedSubscriptionExistsError.openapi_model(),
        },
    },
)
async def reserve(request: Request, body: SubscribeBody) -> SubscribeResponse:
    """Reserves a package subscription to activate after the current one ends."""
    result = service.reserve(
        user_id=request.state.user["id"],
        package_id=body.package_id,
        meal_type=body.meal_type,
        diet_drink=body.diet_drink,
        allergies=body.allergies,
        num_weeks=body.num_weeks,
    )
    return SubscribeResponse(**result)


@router.get(
    "/subscriptions",
    summary="Returns the authenticated user's subscriptions",
    response_description="List of user's package subscriptions",
)
async def get_subscriptions(request: Request) -> list[dict]:
    """Returns all subscriptions for the authenticated user."""
    return service.get_user_subscriptions(request.state.user["id"])


@router.get(
    "/subscriptions/schedule",
    summary="Returns the meal preparation schedule",
    response_description="List of subscriptions for current and upcoming weeks",
    tags=["admin"],
    responses={
        HTTP_403_FORBIDDEN: {
            "model": errors.InsufficientRoleError.openapi_model(),
        },
    },
)
async def get_schedule(
    request: Request,
    weeks: int = Query(default=2, ge=1, le=8, description="Number of weeks to include"),
) -> list[dict]:
    """Returns all subscriptions overlapping the current and upcoming weeks."""
    _require_role(request, Role.ADMIN, Role.OPERATOR)
    return service.get_schedule(num_weeks=weeks)
