class JSONResponse:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code

    def set_cookie(self, *a, **k):
        pass

    def delete_cookie(self, *a, **k):
        pass


class HTMLResponse(str):
    pass


class RedirectResponse:
    def __init__(self, url, status_code=307):
        self.url = url
        self.status_code = status_code
