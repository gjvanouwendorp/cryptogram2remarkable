"""Getypeerde fouten zodat de pipeline onderscheid kan maken tussen
'opnieuw inloggen' en 'de Volkskrant heeft de structuur gewijzigd'."""


class C2RMError(Exception):
    pass


class SessionExpiredError(C2RMError):
    """Het profiel is niet (meer) ingelogd -> handmatig opnieuw inloggen + profiel syncen."""


class StructureChangedError(C2RMError):
    """Verwachte elementen/data ontbreken -> Volkskrant/Braintainment heeft iets gewijzigd."""


class PuzzleNotAvailableError(C2RMError):
    """De nieuwste krantpuzzel op de site is (nog) niet die van deze week."""


class UploadError(C2RMError):
    pass
