"""
Minimal offline test stub for FastAPI. NOT a real implementation -- used
only so router modules can be imported and their pure logic exercised in
an environment with no network access to install the real 'fastapi'
package. Not part of the shipped application.
"""


class APIRouter:
    def __init__(self, prefix="", tags=None):
        self.prefix = prefix
        self.tags = tags or []
        self.routes = []

    def _add(self, method, path):
        def decorator(func):
            self.routes.append((method, self.prefix + path, func))
            return func
        return decorator

    def get(self, path, **kwargs):
        return self._add("GET", path)

    def post(self, path, **kwargs):
        return self._add("POST", path)

    def delete(self, path, **kwargs):
        return self._add("DELETE", path)


class Request:
    def __init__(self, cookies=None, headers=None, json_body=None, url_scheme="http", url_hostname="localhost"):
        self.cookies = cookies or {}
        self.headers = headers or {}
        self._json_body = json_body or {}

        class _URL:
            scheme = url_scheme
            hostname = url_hostname

        self.url = _URL()

    async def json(self):
        return self._json_body


class FastAPI:
    def __init__(self, title="", version=""):
        self.title = title
        self.version = version
        self._startup = []

    def mount(self, *a, **k):
        pass

    def include_router(self, router):
        pass

    def on_event(self, name):
        def decorator(func):
            self._startup.append(func)
            return func
        return decorator

    def get(self, path, **kwargs):
        def decorator(func):
            return func
        return decorator
