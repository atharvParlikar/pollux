from pathlib import Path
import re
import subprocess
from typing import Any

from rich.panel import Panel
from rich.syntax import Syntax

from globals import COMMAND_TIMEOUT, console, logger


def handle_terminal_tool(toolcall: dict[str, Any]) -> str:
    """Handle terminal tool execution with safety checks"""
    params = toolcall.get("params", {})
    command = params.get("command")

    if not command:
        console.print("No command specified for terminal tool")

    dangerous_patterns = [
        r'\brm\s+-rf\s+/',  # matches `rm -rf /`
        r'\bsudo\s+rm\b',
        r'\bformat\b.*[a-z]:',  # matches things like `format c:`
        r'\bdel\b\s+\*',
        r'\bshutdown\b',
        r'\breboot\b',
    ]

    def is_dangerous(command: str) -> bool:
        cmd_lower = command.lower()
        return any(re.search(pattern, cmd_lower) for pattern in dangerous_patterns)

    if is_dangerous(command):
        console.print(f"Dangerous command blocked: {command}")

    logger.info(f"Executing terminal command: {command}")

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
            check=False  # Don't raise on non-zero exit
        )

        # Combine stdout and stderr
        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"

        if result.returncode != 0:
            output += f"\n[EXIT CODE: {result.returncode}]"

        toolcall_result = output or "[No output]"

        return toolcall_result

    except subprocess.TimeoutExpired:
        toolcall_result = f"[Timeout] Command '{command}' took longer than {COMMAND_TIMEOUT} seconds"
        logger.warning(f"Command timeout: {command}")

    except Exception as e:
        toolcall_result = f"[Command Error] {str(e)}"
        logger.error(f"Command execution error: {e}")

    console.print(Panel.fit(
        Syntax(toolcall_result, "bash"),
        title="💻 Terminal Output",
        border_style="magenta"
    ))

    return toolcall_result

def edit_file(file_path: str, start_line: int, end_line: int, new_content: str) -> str:
    path = Path(file_path)

    # Handle file creation if it doesn't exist
    if not path.exists():
        if start_line == 1 and end_line == 0:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new_content, encoding='utf-8')
            return new_content
        else:
            raise FileNotFoundError(f"File not found: {file_path}")

    content = path.read_text(encoding='utf-8')
    lines = content.split('\n')

    # Handle append to end
    if start_line == -1 and end_line == -1:
        lines.append(new_content)
        new_file_content = '\n'.join(lines)
        path.write_text(new_file_content, encoding='utf-8')
        return new_file_content

    # Validate line numbers
    if start_line < 1 or (end_line > 0 and end_line < start_line and not (start_line == end_line + 1)):
        raise ValueError(f"Invalid line numbers: start={start_line}, end={end_line}")

    if start_line == end_line + 1:
        # Insert at position start_line
        insert_pos = start_line - 1
        if insert_pos > len(lines):
            raise IndexError(f"Cannot insert at line {start_line}, file has only {len(lines)} lines")
        lines.insert(insert_pos, new_content)
    else:
        if end_line == 0:
            end_line = start_line
        if start_line > len(lines) or end_line > len(lines):
            raise IndexError(f"Line numbers out of range. File has {len(lines)} lines")

        start_idx = start_line - 1
        end_idx = end_line

        if new_content:
            lines[start_idx:end_idx] = [new_content]
        else:
            del lines[start_idx:end_idx]

    new_file_content = '\n'.join(lines)
    path.write_text(new_file_content, encoding='utf-8')
    return new_file_content
