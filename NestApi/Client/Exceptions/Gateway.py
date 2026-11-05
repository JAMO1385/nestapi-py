from .ApiResponse import APIResponseError

class GatewayError(APIResponseError):
    """Upstream Gateway error (502/504)"""
    pass
