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
