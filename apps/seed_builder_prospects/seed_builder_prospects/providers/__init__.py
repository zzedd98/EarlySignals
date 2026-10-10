"""
Providers : Google (Playwright), Tranco, file_list (CSV/TXT).
Sortie homogène : DiscoveryResult pour le pipeline crawl + score.
"""
from .base import DiscoveryResult, SearchProviderBase
from .file_list import FileListProvider, load_discovery_from_seed_csv
from .google_playwright import GooglePlaywrightProvider
from .tranco import TrancoProvider

__all__ = [
    "DiscoveryResult",
    "SearchProviderBase",
    "FileListProvider",
    "load_discovery_from_seed_csv",
    "GooglePlaywrightProvider",
    "TrancoProvider",
]
