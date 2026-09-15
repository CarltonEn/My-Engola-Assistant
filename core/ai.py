from core import config


def _openai_class():
    try:
        from openai import OpenAI
        return OpenAI
    except ImportError:
        return None


def is_configured() -> bool:
    return bool(config.OPENAI_API_KEY) and _openai_class() is not None


def client():
    OpenAI = _openai_class()
    if OpenAI is None:
        raise RuntimeError("OpenAI package is not installed")
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OpenAI API key is not configured")
    return OpenAI(api_key=config.OPENAI_API_KEY)


def respond(messages, tools=None):
    if not is_configured():
        raise RuntimeError("OpenAI provider is not configured")

    kwargs = {
        "model": config.ENGOLA_MODEL,
        "input": messages,
    }

    if tools:
        kwargs["tools"] = tools

    response = client().responses.create(**kwargs)
    return response.output_text
