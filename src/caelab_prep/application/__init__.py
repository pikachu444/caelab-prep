__all__ = ["PrepSession"]


def __getattr__(name):
    if name == "PrepSession":
        from .session import PrepSession
        return PrepSession
    raise AttributeError(name)
