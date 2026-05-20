from enum import Enum
from enum import IntEnum as SourceIntEnum
from typing import Type


class _EnumBase:
    @classmethod
    def get_member_keys(cls: Type[Enum]) -> list[str]:
        """Retrieve the keys (names) of enum members."""
        return [name for name in cls.__members__.keys()]

    @classmethod
    def get_member_values(cls: Type[Enum]) -> list:
        """Retrieve the values of enum members."""
        return [item.value for item in cls.__members__.values()]


class IntEnum(_EnumBase, SourceIntEnum):
    """Integer-based enum."""

    pass


class StrEnum(_EnumBase, str, Enum):
    """String-based enum."""

    pass


class TimeTypeEnum(StrEnum):
    YEAR = "year"
    QUARTER = "quarter"
    MONTH = "month"
    SPRINT = "sprint"


class SourceEnum(StrEnum):
    HOTJAR = "Hotjar"
    SURVEYMONKEY = "Surveymonkey"
    MANUAL = "Manual"
    CSAT = "CSAT"
    VOC = "VOC"


class TaskStatusEnum(StrEnum):
    CREATED = "created"
    PROCESSING = "processing"
    FAILED = "failed"
    COMPLETED = "completed"


class MenuType(IntEnum):
    """Menu type"""

    directory = 0
    menu = 1
    button = 2


class RoleDataRuleOperatorType(IntEnum):
    """Data rule operator type"""

    AND = 0
    OR = 1


class RoleDataRuleExpressionType(IntEnum):
    """Data rule expression"""

    eq = 0  # ==
    ne = 1  # !=
    gt = 2  # >
    ge = 3  # >=
    lt = 4  # <
    le = 5  # <=
    in_ = 6
    not_in = 7


class MethodType(StrEnum):
    """HTTP request method"""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    OPTIONS = "OPTIONS"


class LoginLogStatusType(IntEnum):
    """Login log status"""

    fail = 0
    success = 1


class BuildTreeType(StrEnum):
    """Build tree structure type"""

    traversal = "traversal"
    recursive = "recursive"


class StatusType(IntEnum):
    """Status type"""

    disable = 0
    enable = 1


class FileType(StrEnum):
    """File type"""

    image = "image"
    video = "video"
