class _Responses:
    def create(self, **kwargs):
        raise RuntimeError("stub OpenAI client: no real API call is made in offline tests")


class OpenAI:
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.responses = _Responses()
