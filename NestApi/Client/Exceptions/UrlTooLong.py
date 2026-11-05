from .ApiResponse import APIResponseError

class URLtooLongError(APIResponseError):
    """Request URI too long (431)"""
    pass

# Alias for consistent naming
UrlTooLongError = URLtooLongError
