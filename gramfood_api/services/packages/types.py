from typing import TypedDict, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from .constants import MealType


class Package(TypedDict):
    """Represents a package in the catalog."""

    id: int
    name: str
    price: float
    is_enabled: bool
    created_at: datetime


class UserPackage(TypedDict):
    """Represents a user's purchased package subscription."""

    id: int
    user_id: int
    package_id: int
    meal_type: MealType
    diet_drink: bool
    allergies: list | None
    start_date: datetime
    end_date: datetime
    is_reserved: bool
    created_at: datetime
