"""
Code formatter using black as a library.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

_PYTHON_SUFFIXES = frozenset({".py", ".pyi", ".pyw"})


def is_python_source_path(file_path: str) -> bool:
    """Return True when path uses a Python handler suffix."""
    return Path(file_path).suffix.lower() in _PYTHON_SUFFIXES


def format_python_source_text(source: str) -> Tuple[str, Optional[str]]:
    """Format Python source text with black (in-memory).

    Returns:
        Tuple of (formatted_source, error_message). On success error is None.
    """
    try:
        import black

        try:
            formatted = black.format_str(source, mode=black.FileMode())
            return formatted, None
        except black.NothingChanged:
            return source, None
    except ImportError:
        return source, "Black formatter not installed"
    except Exception as exc:
        return source, str(exc)


def format_code_with_black(file_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Format Python code using black formatter as a library.

    Args:
        file_path: Path to Python file to format

    Returns:
        Tuple of (success, error_message)
    """
    try:
        import black

        # Read file content
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Format using black
        try:
            # Use black's format_str for more stable API
            # format_str returns just the formatted string
            formatted_content = black.format_str(content, mode=black.FileMode())
            # Check if content changed
            if formatted_content == content:
                # File already formatted
                logger.debug(f"File already formatted: {file_path}")
                return (True, None)
        except black.NothingChanged:
            # File already formatted
            logger.debug(f"File already formatted: {file_path}")
            return (True, None)
        except Exception as e:
            error_msg = f"Black formatting error: {str(e)}"
            logger.warning(error_msg)
            return (False, error_msg)

        # Write formatted content back
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(formatted_content)

        logger.info(f"Code formatted successfully with black: {file_path}")
        return (True, None)

    except ImportError:
        # Fallback to subprocess if black is not available as library
        logger.debug("Black not available as library, falling back to subprocess")
        return _format_with_subprocess(file_path)
    except Exception as e:
        logger.warning(f"Error during formatting: {e}")
        return (False, str(e))


def _format_with_subprocess(file_path: Path) -> Tuple[bool, Optional[str]]:
    """Fallback to subprocess if black library is not available."""
    import subprocess

    try:
        result = subprocess.run(
            ["black", "--quiet", str(file_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            logger.info(f"Code formatted successfully with black: {file_path}")
            return (True, None)
        else:
            error_msg = result.stderr or result.stdout or "Unknown error"
            logger.warning(f"Black formatting failed: {error_msg}")
            return (False, error_msg)
    except subprocess.TimeoutExpired:
        logger.warning("Black formatting timed out")
        return (False, "Formatting timed out")
    except FileNotFoundError:
        logger.warning("Black formatter not found, skipping formatting")
        return (False, "Black formatter not installed")
    except Exception as e:
        logger.warning(f"Error during formatting: {e}")
        return (False, str(e))
