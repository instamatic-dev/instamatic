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

class HolderControllerError(Exception):
    pass

class HolderCommunicationError(Exception):
    pass

exception_list = {
    'TEMValueError': TEMValueError,
    'TEMCommunicationError': TEMCommunicationError,
    'TEMValueError': TEMValueError,
    'JEOLValueError': JEOLValueError,
    'FEIValueError': FEIValueError,
    'TEMControllerError   ': TEMControllerError,
    'AttributeError': AttributeError,
    'AssertionError': AssertionError,
    'ConnectionError': ConnectionError,
    'Exception': Exception,
    'FileNotFoundError': FileNotFoundError,
    'IndexError': IndexError,
    'InterruptedError': InterruptedError,
    'IOError': IOError,
    'KeyError': KeyError,
    'NameError': NameError,
    'NotImplementedError': NotImplementedError,
    'OSError': OSError,
    'PermissionError': PermissionError,
    'RuntimeError': RuntimeError,
    'StopIteration': StopIteration,
    'TypeError': TypeError,
    'ValueError': ValueError,
    'WindowsError': WindowsError,
}
