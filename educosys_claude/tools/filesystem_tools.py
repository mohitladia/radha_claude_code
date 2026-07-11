"""
Filesystem tools for the agent: read, write, append, list, exists, delete.

These are DANGEROUS operations (write/append/delete) and require
Human-in-the-Loop approval via agent/factory.py interrupt_on config.
"""

import os
from langchain.tools import tool


_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit for safety


@tool
def read_file(file_path: str) -> str:
    """
    Read and return the contents of a file.

    Args:
        file_path: Absolute or relative path to the file.

    Returns:
        File contents as string, or error message.
    """
    if not file_path or not file_path.strip():
        return "Error: file path cannot be empty"

    # Resolve relative paths for security/consistency
    file_path = os.path.abspath(file_path)

    if not os.path.exists(file_path):
        return f"Error: file not found: {file_path}"
    if not os.path.isfile(file_path):
        return f"Error: path is not a file: {file_path}"

    size = os.path.getsize(file_path)
    if size > _MAX_FILE_SIZE_BYTES:
        return f"Error: file too large ({size} bytes). Max allowed is {_MAX_FILE_SIZE_BYTES} bytes"

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        return f"Error: file is not valid UTF-8 text: {file_path}"
    except PermissionError:
        return f"Error: permission denied: {file_path}"
    except Exception as e:
        return f"Error: {e}"


@tool
def write_file(file_path: str, content: str) -> str:
    """
    Write content to a file, creating it and any parent directories if needed.

    ⚠️ DESTRUCTIVE: Overwrites existing file without warning.
    Requires HITL approval (configured in agent/factory.py).

    Args:
        file_path: Absolute or relative path to write.
        content: Text content to write.

    Returns:
        Success message or error.
    """
    if not file_path or not file_path.strip():
        return "Error: file path cannot be empty"

    file_path = os.path.abspath(file_path)

    try:
        # Create parent directories if they don't exist
        if os.path.dirname(file_path):
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Written to {file_path}"
    except PermissionError:
        return f"Error: permission denied: {file_path}"
    except Exception as e:
        return f"Error: {e}"


@tool
def append_file(file_path: str, content: str) -> str:
    """
    Append content to an existing file.

    ⚠️ DESTRUCTIVE: Modifies file.
    Requires HITL approval (configured in agent/factory.py).

    Args:
        file_path: Absolute or relative path to file (must exist).
        content: Text to append.

    Returns:
        Success message or error.
    """
    if not file_path or not file_path.strip():
        return "Error: file path cannot be empty"

    file_path = os.path.abspath(file_path)

    if not os.path.exists(file_path):
        return f"Error: file not found: {file_path}"
    if not os.path.isfile(file_path):
        return f"Error: path is not a file: {file_path}"

    try:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(content)
        return f"Appended to {file_path}"
    except PermissionError:
        return f"Error: permission denied: {file_path}"
    except Exception as e:
        return f"Error: {e}"


@tool
def delete_file(file_path: str) -> str:
    """
    Delete a file.

    ⚠️ DESTRUCTIVE: Permanently removes file.
    Requires HITL approval (configured in agent/factory.py).

    Args:
        file_path: Absolute or relative path to file (must exist).

    Returns:
        Success message or error.
    """
    if not file_path or not file_path.strip():
        return "Error: file path cannot be empty"

    file_path = os.path.abspath(file_path)

    if not os.path.exists(file_path):
        return f"Error: file not found: {file_path}"
    if not os.path.isfile(file_path):
        return f"Error: path is not a file (use a directory tool for directories): {file_path}"

    try:
        os.remove(file_path)
        return f"Deleted {file_path}"
    except PermissionError:
        return f"Error: permission denied: {file_path}"
    except Exception as e:
        return f"Error: {e}"


@tool
def list_directory(directory: str) -> str:
    """
    List files and subdirectories inside a directory.

    Args:
        directory: Absolute or relative path to directory.

    Returns:
        Newline-separated sorted list of entries, or "(empty directory)".
    """
    if not directory or not directory.strip():
        return "Error: directory cannot be empty"

    directory = os.path.abspath(directory)

    if not os.path.exists(directory):
        return f"Error: directory not found: {directory}"
    if not os.path.isdir(directory):
        return f"Error: path is not a directory: {directory}"

    try:
        entries = os.listdir(directory)
        return "\n".join(sorted(entries)) if entries else "(empty directory)"
    except PermissionError:
        return f"Error: permission denied: {directory}"
    except Exception as e:
        return f"Error: {e}"


@tool
def file_exists(file_path: str) -> str:
    """
    Check whether a file or directory exists.

    Args:
        file_path: Path to check.

    Returns:
        "True" or "False" as string (for tool output compatibility).
    """
    if not file_path or not file_path.strip():
        return "Error: file path cannot be empty"
    return str(os.path.exists(file_path))