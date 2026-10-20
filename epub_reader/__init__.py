"""EpubReader package."""
from .epub import Epub, EpubError
from .store import Store, DEFAULT_SETTINGS
from .library import Library

__all__ = ["Epub", "EpubError", "Store", "DEFAULT_SETTINGS", "Library"]
