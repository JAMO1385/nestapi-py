from .NestError import NestError

class APIResponseError(NestError):
    """Base error returned by the API or its edge proxy.

    Both the original project's capitalized keyword arguments and conventional
    Python attributes are supported for backwards compatibility.
    """

    def __init__(
        self,
        Message: str = "",
        Status_Code: int = 0,
        Error_Code: str | None = None,
        *,
        details=None,
        response=None,
    ):
        super().__init__(Message)
        self.Message = Message
        self.Status_code = Status_Code
        self.Status_Code = Status_Code
        self.status_code = Status_Code
        self.Error_Code = Error_Code
        self.error_code = Error_Code
        self.message = Message
        self.details = details
        self.response = response

    def __str__(self):
        prefix = f"[{self.Status_code}"
        if self.Error_Code:
            prefix += f" : {self.Error_Code}"
        return f"{prefix}] {self.Message}"
