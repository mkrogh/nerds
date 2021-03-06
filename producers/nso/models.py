class Equipment:
    def __init__(self):
        self.name = ''
        self.version = ''
        self.model = ''
        self.interfaces = []

    def to_json(self):
        j = vars(self).copy()
        j['interfaces'] = [i.to_json() for i in self.interfaces]
        return j


class Switch(Equipment):
    pass


class Router(Equipment):
    def __init__(self):
        super().__init__()
        self.bgp_peerings = []
        self.hardware = {}

    def to_json(self):
        j = vars(self).copy()
        j['interfaces'] = [i.to_json() for i in self.interfaces]
        j['bgp_peerings'] = [p.to_json() for p in self.bgp_peerings]
        if self.hardware:
            j['hardware'] = self.hardware
        return j


class Interface:
    def __init__(self):
        self.name = ''
        self.bundle = ''
        self.description = ''
        self.vlantagging = ''
        self.tunneldict = []
        self.inactive = False
        # Unit dict is a list of dictionaries containing units to
        # interfaces, should be index like {'unit': 'name',
        # 'description': 'foo', 'vlanid': 'bar', 'address': 'xyz'}
        self.unitdict = []

    def to_json(self):
        return {
            'name': self.name,
            'bundle': self.bundle,
            'description': self.description,
            'vlantagging': self.vlantagging,
            'tunnels': self.tunneldict,
            'units': self.unitdict,
            'inactive': self.inactive,
        }


class BgpPeering:
    def __init__(self):
        self.type = None
        self.remote_address = None
        self.description = None
        self.local_address = None
        self.group = None
        self.as_number = None

    def to_json(self):
        return vars(self).copy()
