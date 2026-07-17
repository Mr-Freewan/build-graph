"""Shared CLI helpers for the doc-sync tools (related / links)."""

from pathlib import Path


class Colors:
    """ANSI color codes for terminal output."""

    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def print_separator() -> None:
    """Print a visual separator line."""
    print("─" * 100)


def is_code_or_config_file(file_path: Path) -> bool:
    """Check if a file is a code or configuration file that should be checked.

    Returns:
        True if file is .py, .md, or config file
    """
    code_extensions = {".py", ".md"}
    config_extensions = {
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".json",
        ".conf",
        ".env",
        ".config",
    }
    return file_path.suffix.lower() in code_extensions | config_extensions
