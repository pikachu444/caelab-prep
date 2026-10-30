"""Native desktop presentation; model ownership remains in the application layer."""

__all__ = ["MainWindow", "run"]


def __getattr__(name):
    if name in __all__:
        from . import main_window
        return getattr(main_window, name)
    raise AttributeError(name)
