import json5

attrdict = type("attrdict", (dict,), {
    "__getattr__": dict.__getitem__,
    "__setattr__": dict.__setitem__,
    "__delattr__": dict.__delitem__})


class Config:
    __slots__ = (
        "_data",
    )

    @classmethod
    def from_file(cls, fp, **kwargs):
        self = cls()

        try:
            with open(fp) as f:
                self._data = json5.load(f, encoding=kwargs.pop("encoding", "utf-8"),
                                        allow_duplicate_keys=kwargs.pop("allow_duplicate_keys", False),
                                        object_hook=self._to_attrdict, **kwargs)
        except FileNotFoundError:
            self._data = {}

        return self

    @classmethod
    def from_dict(cls, dct):
        if not isinstance(dct, dict):
            raise TypeError("dct must be a dictionary.")

        self = cls()
        self._data = self._to_attrdict(dct)

        return self

    @classmethod
    def from_string(cls, string, **kwargs):
        self = cls()

        self._data = json5.loads(string, encoding=kwargs.pop("encoding", "utf-8"),
                                 allow_duplicate_keys=kwargs.pop("allow_duplicate_keys", False),
                                 object_hook=self._to_attrdict, **kwargs)

        return self

    def _to_attrdict(self, d):
        return attrdict(d)

    def items(self):
        return self._data.items()

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def get(self, item):
        return self._data.get(item)

    def __contains__(self, item):
        return item in self._data

    def __getitem__(self, item):
        return self._data[item]

    def __getattr__(self, item):
        return self.__getitem__(item)
