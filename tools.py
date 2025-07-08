# pyright: reportUnusedCallResult=false

from rich.console import Console
from pathlib import Path

console = Console()

def edit_file(file_path: str, old_text: str, new_text: str) -> str:
    """
    Edit a file by replacing the first occurrence of old_text with new_text.
    Includes validation and detailed error reporting for LLM usage.

    Args:
        file_path: Path to the file to edit
        old_text: Text to find and replace (must match exactly, including whitespace)
        new_text: Text to replace the old_text with

    Returns:
        Success message with edited file content or error message
    """
    # Input validation
    if len(old_text) == 0:
        # New text can be empty because it's possible to delete text
        return "[ERROR] old_text cannot be empty"

    if old_text == new_text:
        return "[ERROR] old_text and new_text are identical - no changes needed"

    # Read file contents
    file_contents = read_file(file_path)
    if file_contents.startswith("[ERROR]"):
        return file_contents

    # Find and validate the replacement text
    if file_contents.find(old_text) == -1:
        # Provide helpful context for why the match failed
        return f"[ERROR] old_text not found in {file_path}\nMake sure the text matches exactly (including whitespace and indentation)"

    try:
        # Perform the replacement
        edited_file = file_contents.replace(old_text, new_text, 1)  # Only replace first occurrence

        # Write changes
        Path(file_path).write_text(edited_file, encoding='utf-8')

        return f"File edited successfully\n---\nEdited content:\n{edited_file}"

    except Exception as e:
        return f"[ERROR] Failed to edit file: {str(e)}"


def read_file(file_path: str) -> str:
    """
    Read and return the complete contents of a file.

    Args:
        file_path: Path to the file to read

    Returns:
        File contents as string or error message
    """
    try:
        content = Path(file_path).read_text(encoding='utf-8')

        # Truncate very large files to prevent context window issues
        if len(content) > 50000:  # ~50KB limit
            return content[:50000] + f"\n\n[TRUNCATED - File is {len(content)} characters, showing first 50,000]"

        return content

    except FileNotFoundError:
        return f"[ERROR] File not found: {file_path}"
    except PermissionError:
        return f"[ERROR] Permission denied: Cannot read {file_path}"
    except UnicodeDecodeError:
        return f"[ERROR] Cannot read file {file_path}: File appears to be binary or uses unsupported encoding"
    except Exception as e:
        return f"[ERROR] Unexpected error reading {file_path}: {str(e)}"

