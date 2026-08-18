import sys
from pathlib import Path


def is_windows_host() -> bool:
    """Return True when running on Windows."""

    return sys.platform.startswith("win32")


def is_macos_host() -> bool:
    """Return True when running on macOS."""

    return sys.platform.startswith("darwin")


def to_wsl_path(path: str | Path) -> str:
    """Convert a Windows absolute path to a WSL path, leaving Unix-style paths intact."""

    path_str = str(path).replace("\\", "/")
    if len(path_str) >= 2 and path_str[1] == ":" and path_str[0].isalpha():
        drive = path_str[0].lower()
        rest = path_str[2:]
        if not rest.startswith("/"):
            rest = "/" + rest
        return f"/mnt/{drive}{rest}"
    return path_str


def adapt_path_for_host_tool(path: str | Path) -> str:
    """Return a subprocess-safe path string for the current host tool execution mode."""

    resolved_path = Path(path).resolve()
    if is_windows_host():
        return to_wsl_path(resolved_path)
    return str(resolved_path)


def unix_tool_prefix(tool_name: str) -> list[str]:
    """Return the command prefix for a Unix-style hardware tool on the current host."""

    if is_windows_host():
        return ["wsl", tool_name]
    return [tool_name]


def unix_tool_platform_mode() -> str:
    """Describe the execution mode used for Unix-style hardware tools."""

    if is_windows_host():
        return "windows_wsl"
    if is_macos_host():
        return "native_macos"
    return "native_linux"
