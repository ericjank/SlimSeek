class SlimSeekError(Exception):
    pass


class DocumentError(SlimSeekError):
    pass


class DuplicateDocumentError(SlimSeekError):
    pass


class DocumentNotFoundError(SlimSeekError):
    pass


class ProviderError(SlimSeekError):
    pass


class IndexCompatibilityError(SlimSeekError):
    pass
