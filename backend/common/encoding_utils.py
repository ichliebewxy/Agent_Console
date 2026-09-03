"""Encoding-safe console helpers for Windows and redirected logs."""
import sys


def configure_stdio_encoding():
    """Prevent console logging from crashing on characters outside the active codepage."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="backslashreplace")
            except Exception:
                pass


def safe_print(message: object = ""):
    """Print without letting UnicodeEncodeError escape into request handling."""
    text = str(message)
    try:
        print(text)
    except UnicodeEncodeError:
        safe_text = text.encode(sys.stdout.encoding or "utf-8", errors="backslashreplace").decode(
            sys.stdout.encoding or "utf-8",
            errors="replace",
        )
        print(safe_text)
