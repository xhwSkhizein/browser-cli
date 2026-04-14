"""browser-cli package."""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]


def _resolve_version() -> str:
    for distribution_name in (
        "browser-control-and-automation-cli",
        "browserctl",
        "browser-cli",
    ):
        try:
            return version(distribution_name)
        except PackageNotFoundError:
            continue
    return "0+unknown"


__version__ = _resolve_version()
