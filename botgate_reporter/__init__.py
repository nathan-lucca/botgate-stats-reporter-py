from .reporter import BotGateReporter

try:
    from importlib.metadata import version

    __version__ = version("botgate-stats-reporter-py")
except Exception:
    __version__ = "1.0.1"

__all__ = ["BotGateReporter"]
