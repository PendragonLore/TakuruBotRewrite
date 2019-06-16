import json5


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
                                        allow_duplicate_keys=kwargs.pop("allow_duplicate_keys", False), **kwargs)
        except FileNotFoundError:
            self._data = {}

        return self

    @classmethod
    def from_dict(cls, dct):
        if not isinstance(dct, dict):
            raise TypeError("dct must be a dictionary.")

        self = cls()
        self._data = dct

        return self

    @classmethod
    def from_string(cls, string, **kwargs):
        self = cls()

        self._data = json5.loads(string, encoding=kwargs.pop("encoding", "utf-8"),
                                 allow_duplicate_keys=kwargs.pop("allow_duplicate_keys", False), **kwargs)

        return self

    def items(self):
        return self._data.items()

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def get(self, item):
        return self._data.get(item)

    def pop(self, item):
        return self._data.pop(item)

    def __contains__(self, item):
        return item in self._data

    def __getitem__(self, item):
        return self._data[item]

    def __delitem__(self, key):
        del self._data[key]

    def __getattr__(self, item):
        return self.__getitem__(item)

    def __delattr__(self, item):
        return self.__delitem__(item)
