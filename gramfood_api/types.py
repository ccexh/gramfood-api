from typing import TypedDict, NotRequired, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .services.types import User, OTP, Session


class _ConfigMain(TypedDict):
    development: bool
    request_timeout: float
    temp_path: str


class _ConfigLog(TypedDict):
    store: bool
    console_traceback: bool
    console_level: str
    storage_level: str
    storage_size: int
    path: str


class _ConfigDatabase(TypedDict):
    backup_interval: int
    maximum_backups: int
    path: str


class _ConfigApi(TypedDict):
    ui: bool
    socket_path: str
    graceful_shutdown: float


class _ConfigAuthentication(TypedDict):
    otp_length: int
    otp_expiry: int
    otp_max_verify_attempts: int
    otp_rate_limit_max_requests: int
    otp_rate_limit_window: int
    default_session_max_age: int
    kiosk_session_max_age: int
    token_hash_salt: str


class _ConfigSms(TypedDict):
    template_id: int
    api_key: str


class Config(TypedDict):
    main: _ConfigMain
    log: _ConfigLog
    database: _ConfigDatabase
    api: _ConfigApi
    authentication: _ConfigAuthentication
    sms: _ConfigSms


class DatabaseSchema(TypedDict):
    users: list[User]
    otp_codes: list[OTP]
    sessions: list[Session]


class SerializedError(TypedDict):
    type: str
    message: str
    group: NotRequired[str]
    code: NotRequired[int]
    cause: NotRequired[list[SerializedError]]
    payload: NotRequired[Any]


class HTTPSerializedError(TypedDict):
    details: list[SerializedError]


class DataUnits(TypedDict):
    B: str
    kB: str
    MB: str
    GB: str
    TB: str
    PB: str
