from .ApiResponse import APIResponseError

class ServiceUnavailableError(APIResponseError):
    """NestAPI service temporarily unavailable (503)"""
    pass
