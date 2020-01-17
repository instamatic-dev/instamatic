class TEMCommunicationError(ConnectionError):
    pass


class TEMValueError(ValueError):
    pass


class JEOLValueError(TEMValueError):
    pass


class FEIValueError(TEMValueError):
    pass


class TEMControllerError(Exception):
    pass
