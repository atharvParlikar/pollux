import subprocess
from openai.types.chat import ChatCompletionMessageParam
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from tools import edit_file, read_file

console = Console()

def extract_command(response: str) -> str | None:
    start = response.find("<terminal>")
    end = response.find("</terminal>")
    if start == -1 or end == -1:
        return None
    return response[start + len("<terminal>"):end].strip()


def handle_read_file(content: str, messages: list[ChatCompletionMessageParam]) -> bool:
    if "<read_file>" not in content:
        return False

    file_path = content.split("<read_file>")[1].split("</read_file>")[0].strip()
    console.print(Panel(f"Reading file: {file_path}", title="Tool Use: read_file", style="cyan"))
    try:
        file_content = read_file(file_path)
        console.print(Panel(file_content, title="File Content", border_style="blue"))
        messages.append({"role": "user", "content": f"<file_content>{file_content}</file_content>"})
    except Exception as e:
        error_msg = f"[ERROR] Could not read file: {str(e)}"
        console.print(Panel(error_msg, title="File Read Error", border_style="red"))
        messages.append({"role": "user", "content": f"<file_content>{error_msg}</file_content>"})
    return True


def handle_edit_file(content: str, messages: list[ChatCompletionMessageParam]) -> bool:
    if "<edit_file>" not in content:
        return False

    edit_content = content.split('<edit_file>')[1].split('</edit_file>')[0].strip()
    console.print(Panel(f"Editing file with:\n{edit_content}", title="Tool Use: edit_file", style="yellow"))

    try:
        def extract_between(marker1, marker2):
            start = edit_content.find(marker1) + len(marker1)
            end = edit_content.find(marker2)
            return edit_content[start:end].strip()

        file_path = extract_between("file_path:", "old_text:")
        old_text = extract_between("old_text:", "new_text:")
        new_text = edit_content.split("new_text:")[1].strip()

        result = edit_file(file_path, old_text, new_text)
        console.print(Panel(result, title="Edit Result", border_style="green"))
        messages.append({"role": "user", "content": f"<edit_result>{result}</edit_result>"})

    except Exception as e:
        error_msg = f"[ERROR] Could not edit file: {str(e)}"
        console.print(Panel(error_msg, title="File Edit Error", border_style="red"))
        messages.append({"role": "user", "content": f"<edit_result>{error_msg}</edit_result>"})
    return True


def handle_terminal_command(content: str, messages: list[ChatCompletionMessageParam]) -> bool:
    if "<terminal>" not in content:
        return False

    command = extract_command(content)
    if not command:
        return False

    console.print(Panel.fit(Syntax(command, "bash", theme="monokai", line_numbers=False), title="Executing Command"))
    try:
        result = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as e:
        result = f"[ERROR]\n{e.output}"

    if len(result) > 10000:
        result = "[ERROR] Output too large, trim output to fit context window"

    console.print(Panel(result.strip(), title="Command Output", border_style="green"))
    messages.append({"role": "user", "content": f"<output>{result}</output>"})
    return True


def extract_thinking(content: str):
    if "<thinking>" in content and "</thinking>" in content:
        thinking = content.split("<thinking>")[1].split("</thinking>")[0].strip()
        console.print(Panel(thinking, title="Thinking", style="dim italic"))
