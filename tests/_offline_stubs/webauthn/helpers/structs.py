class AuthenticatorAttachment:
    PLATFORM = "platform"


class ResidentKeyRequirement:
    REQUIRED = "required"


class UserVerificationRequirement:
    REQUIRED = "required"


class AuthenticatorSelectionCriteria:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class PublicKeyCredentialDescriptor:
    def __init__(self, id=None):
        self.id = id
