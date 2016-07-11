import time
import loggedmethods


class BaseInstrument(object):
    logged_methods_on = False
    capabilities = (
        {'name': 'SystemTime', 'type': 'property'},
    )

    def __init__(self):
        pass

    def getSystemTime(self):
        return time.time()

    def getCapabilities(self):
        implemented = []
        for cap in self.capabilities:
            found = {'name': cap['name'], 'implemented': []}
            if cap['type'] == 'property':
                for op in ('set', 'get'):
                    attr = op + cap['name']
                    if hasattr(self, attr):
                        found['implemented'].append(op)
            elif cap['type'] == 'method':
                if hasattr(self, cap['name']):
                    found['implemented'].append('call')
            if found['implemented']:
                implemented.append(found)
        return implemented

    def getHeader(self):
        ret = {}
        for d in self.getCapabilities():
            if 'get' in d["implemented"]:
                try:
                    val = getattr(self, "get"+d["name"])()
                except Exception as e:
                    val = repr(e)
                ret[d["name"]] = val
        return ret