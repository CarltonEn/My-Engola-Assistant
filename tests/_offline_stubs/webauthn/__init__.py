class _Options:
    def __init__(self, challenge=b"stub-challenge"):
        self.challenge = challenge


def generate_registration_options(**kwargs):
    return _Options()


def generate_authentication_options(**kwargs):
    return _Options()


def options_to_json(options):
    return '{"challenge": "stub"}'


def base64url_to_bytes(s):
    return b"stub"


class _Verification:
    credential_id = b"stub-id"
    credential_public_key = b"stub-key"
    sign_count = 0
    new_sign_count = 1


def verify_registration_response(**kwargs):
    return _Verification()


def verify_authentication_response(**kwargs):
    return _Verification()
