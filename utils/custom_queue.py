import asyncio
import collections
import random


class CustomQueue:
    def __init__(self, *, loop=None):
        self.loop = loop or asyncio.get_event_loop()

        self._internal = []
        self._getters = collections.deque()

    def __repr__(self):
        return "<Queue _internal={0._internal} _getters={0._getters} empty={0.empty}>".format(self)

    @property
    def empty(self):
        return not self._internal

    def fetch_all(self):
        return self._internal.copy()

    def __iter__(self):
        return iter(self._internal)

    def __len__(self):
        return len(self._internal)

    def __bool__(self):
        return bool(self._internal)

    async def wait_get(self, timeout=None):
        while self.empty:
            future = self.loop.create_future()
            self._getters.append(future)

            try:
                await asyncio.wait_for(future, timeout=timeout)
            except Exception:
                future.cancel()
                try:
                    self._getters.remove(future)
                except ValueError:
                    pass
                if not self.empty and not future.cancelled():
                    self._wakeup_getter()
                raise

        return self._internal.pop(0)

    def pop(self, index):
        return self._internal.pop(index)

    def popleft(self):
        return self.pop(0)

    def shuffle(self):
        random.shuffle(self._internal)

    def clear(self):
        self._internal.clear()

    def _wakeup_getter(self):
        while self._getters:
            getter = self._getters.popleft()

            if not getter.done():
                getter.set_result(None)
                break

    def put(self, item, *, index=None):
        if index is None:
            self._internal.append(item)
        else:
            self._internal.insert(index, item)
        self._wakeup_getter()

    def putleft(self, item):
        self._internal.insert(0, item)
        self._wakeup_getter()
