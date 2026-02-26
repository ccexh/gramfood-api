import logging
import sqlite3

import jdatetime

from .constants import MealType
from .database import PackageRepository
from .types import Package, UserPackage
from .errors import (
    PackageNotFoundError,
    PackageDisabledError,
    InvalidWeekSelectionError,
    ActiveSubscriptionExistsError,
    ActiveSubscriptionNotFoundError,
    ReservedSubscriptionExistsError,
)

logger = logging.getLogger(__name__)

# In the Jalali calendar, the week starts on Saturday (weekday index 0).
# Friday (weekday index 6) has no meals.
MAX_WEEKS = 4
FRIDAY_WEEKDAY = 5  # jdatetime weekday: Sat=0 ... Fri=5 (ISO-like for Jalali)


class PackageService:
    """Handles package subscription business logic."""

    def __init__(self, connection: sqlite3.Connection | None = None) -> None:
        self._connection = connection

    @staticmethod
    def _jalali_week_start(jalali_date: jdatetime.date) -> jdatetime.date:
        """Returns the Saturday (start of the Jalali week) for the given date."""
        return jalali_date - jdatetime.timedelta(days=jalali_date.weekday())

    @staticmethod
    def _compute_date_range(
        num_weeks: int,
    ) -> tuple[jdatetime.date, jdatetime.date]:
        """Computes the start and end dates for a subscription.

        The subscription starts from the beginning of the next Jalali week
        (Saturday) and spans the requested number of weeks.

        Args:
            `num_weeks`:
                Number of weeks (1 to ``MAX_WEEKS``).

        Returns:
            A tuple of `(start_date, end_date)` as Jalali dates.

        Raises:
            ``InvalidWeekSelectionError``:
                If ``num_weeks`` is not between 1 and ``MAX_WEEKS``.
        """
        if not 1 <= num_weeks <= MAX_WEEKS:
            raise InvalidWeekSelectionError(
                f"Number of weeks must be between 1 and {MAX_WEEKS}, got {num_weeks}.",
                payload={"num_weeks": num_weeks, "max_weeks": MAX_WEEKS},
            )

        today = jdatetime.date.today()
        # Starting from the next week's Saturday
        next_saturday = PackageService._jalali_week_start(today) + jdatetime.timedelta(
            days=7
        )
        # Ending on Thursday of the last selected week (6 days after Saturday,
        # since Friday is excluded)
        end_date = next_saturday + jdatetime.timedelta(days=(num_weeks * 7) - 2)

        return next_saturday, end_date

    # -- Package catalog operations --

    def get_available_packages(self) -> list[Package]:
        """Returns all enabled packages available for purchase."""
        with PackageRepository(self._connection) as repo:
            return repo.get_enabled_packages()

    def get_all_packages(self) -> list[Package]:
        """Returns all packages including disabled ones (admin view)."""
        with PackageRepository(self._connection) as repo:
            return repo.get_all_packages()

    def create_package(self, name: str, price: float) -> int:
        """Creates a new package and returns its ID.

        Raises:
            ``DuplicatePackageNameError``:
                If a package with the given name already exists.
        """
        with PackageRepository(self._connection) as repo:
            package_id = repo.add_package(name, price)
            logger.info(f"Package created | name={name} price={price} id={package_id}")
            return package_id

    def update_package(
        self,
        package_id: int,
        *,
        name: str | None = None,
        price: float | None = None,
        is_enabled: bool | None = None,
    ) -> None:
        """Updates a package's fields.

        Raises:
            ``PackageNotFoundError``:
                If the package does not exist.
            ``DuplicatePackageNameError``:
                If the new name conflicts with an existing package.
        """
        with PackageRepository(self._connection) as repo:
            if repo.get_package_by_id(package_id) is None:
                raise PackageNotFoundError(package_id)

            repo.update_package(
                package_id, name=name, price=price, is_enabled=is_enabled
            )
            logger.info(f"Package updated | id={package_id}")

    # -- Subscription operations --

    def subscribe(
        self,
        *,
        user_id: int,
        package_id: int,
        meal_type: MealType,
        diet_drink: bool,
        allergies: list | None,
        num_weeks: int,
    ) -> dict:
        """Purchases a new package subscription for the user.

        Raises:
            ``PackageNotFoundError``:
                If the package does not exist.
            ``PackageDisabledError``:
                If the package is not enabled.
            ``ActiveSubscriptionExistsError``:
                If the user already has an active subscription.
            ``InvalidWeekSelectionError``:
                If ``num_weeks`` is invalid.
        """
        start_jalali, end_jalali = self._compute_date_range(num_weeks)
        start_date = start_jalali.togregorian()
        end_date = end_jalali.togregorian()

        with PackageRepository(self._connection) as repo:
            package = repo.get_package_by_id(package_id)
            if package is None:
                raise PackageNotFoundError(package_id)
            if not package["is_enabled"]:
                raise PackageDisabledError(package_id)

            if repo.get_active_subscription(user_id) is not None:
                raise ActiveSubscriptionExistsError(user_id)

            record_id = repo.add_user_package(
                user_id=user_id,
                package_id=package_id,
                meal_type=meal_type,
                diet_drink=diet_drink,
                allergies=allergies,
                start_date=start_date,
                end_date=end_date,
                is_reserved=False,
            )

            logger.info(
                f"Package subscribed | "
                f"user_id={user_id} package_id={package_id} "
                f"start={start_jalali} end={end_jalali}"
            )
            return {
                "id": record_id,
                "start_date": str(start_jalali),
                "end_date": str(end_jalali),
            }

    def reserve(
        self,
        *,
        user_id: int,
        package_id: int,
        meal_type: MealType,
        diet_drink: bool,
        allergies: list | None,
        num_weeks: int,
    ) -> dict:
        """Reserves a package subscription to start after the current one ends.

        Raises:
            ``PackageNotFoundError``:
                If the package does not exist.
            ``PackageDisabledError``:
                If the package is not enabled.
            ``ActiveSubscriptionNotFoundError``:
                If the user has no active subscription.
            ``ReservedSubscriptionExistsError``:
                If the user already has a reserved subscription.
            ``InvalidWeekSelectionError``:
                If ``num_weeks`` is invalid.
        """
        with PackageRepository(self._connection) as repo:
            package = repo.get_package_by_id(package_id)
            if package is None:
                raise PackageNotFoundError(package_id)
            if not package["is_enabled"]:
                raise PackageDisabledError(package_id)

            active = repo.get_active_subscription(user_id)
            if active is None:
                raise ActiveSubscriptionNotFoundError(user_id)
            if repo.get_reserved_subscription(user_id) is not None:
                raise ReservedSubscriptionExistsError(user_id)

            # Reserved subscription starts the day after the active one ends
            active_end = active["end_date"]
            active_end_jalali = jdatetime.date.fromgregorian(date=active_end.date())
            # Moving to the next Saturday after the active subscription ends
            next_saturday = self._jalali_week_start(
                active_end_jalali
            ) + jdatetime.timedelta(days=7)

            if not 1 <= num_weeks <= MAX_WEEKS:
                raise InvalidWeekSelectionError(
                    f"Number of weeks must be between 1 and {MAX_WEEKS}, "
                    f"got {num_weeks}.",
                    payload={"num_weeks": num_weeks, "max_weeks": MAX_WEEKS},
                )

            end_jalali = next_saturday + jdatetime.timedelta(days=(num_weeks * 7) - 2)
            start_date = next_saturday.togregorian()
            end_date = end_jalali.togregorian()

            record_id = repo.add_user_package(
                user_id=user_id,
                package_id=package_id,
                meal_type=meal_type,
                diet_drink=diet_drink,
                allergies=allergies,
                start_date=start_date,
                end_date=end_date,
                is_reserved=True,
            )

            logger.info(
                f"Package reserved | "
                f"user_id={user_id} package_id={package_id} "
                f"start={next_saturday} end={end_jalali}"
            )
            return {
                "id": record_id,
                "start_date": str(next_saturday),
                "end_date": str(end_jalali),
            }

    def get_user_subscriptions(self, user_id: int) -> list[UserPackage]:
        """Returns all subscriptions for the given user."""
        with PackageRepository(self._connection) as repo:
            return [dict(row) for row in repo.get_user_subscriptions(user_id)]

    def get_schedule(self, num_weeks: int = 2) -> list[dict]:
        """Returns subscriptions for the current and upcoming weeks.

        Used by operators to view the meal preparation schedule.

        Args:
            `num_weeks`:
                Number of weeks to include in the schedule (default: 2).
        """
        today = jdatetime.date.today()
        week_start = self._jalali_week_start(today)
        schedule_end = week_start + jdatetime.timedelta(days=(num_weeks * 7) - 1)

        start_gregorian = week_start.togregorian()
        end_gregorian = schedule_end.togregorian()

        with PackageRepository(self._connection) as repo:
            return [
                dict(row)
                for row in repo.get_subscriptions_in_range(
                    start_gregorian, end_gregorian
                )
            ]
