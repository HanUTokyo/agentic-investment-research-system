class UpstreamServiceError(RuntimeError):
    """A safe-to-display category for a failed dependency request."""


class UpstreamNotFoundError(UpstreamServiceError):
    pass


class UpstreamTimeoutError(UpstreamServiceError):
    pass


class UpstreamProtocolError(UpstreamServiceError):
    pass
