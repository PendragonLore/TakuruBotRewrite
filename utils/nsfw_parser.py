from lxml import etree


class NSFWParser:
    def __init__(self, ctx, url, request_params, paths, *, parser=None):
        self.ctx = ctx
        self.url = url

        self.request_params = request_params

        self.paths = paths
        self.parser = parser or etree.HTMLParser(encoding="utf-8")

        self.html = None
        self.nodes = None

    async def request(self):
        self.html = html = await self.ctx.get(self.url, **self.request_params)
        self.nodes = etree.fromstring(html, parser=self.parser)

    async def parse(self):
        await self.request()

        xpaths = [path.xpath(self.nodes) for path in self.paths]

        if len(xpaths) == 1:
            for result in xpaths[0]:
                yield result
        else:
            for result in zip(*xpaths):
                yield result


class Node:
    def __init__(self, path):
        self.path = path
        self.slice = slice(None, None, None)

    def __getitem__(self, item):
        if not isinstance(item, slice):
            raise TypeError("Node supports only slicing.")
        self.slice = item
        return self

    def xpath(self, nodes):
        return nodes.xpath(self.path)[self.slice]
