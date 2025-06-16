# pyright: reportUnusedCallResult=false

import os
import subprocess
from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.prompt import Prompt
from rich.markdown import Markdown
from textual.app import App, ComposeResult
from textual.widgets import Input, Static
from typing import Any

from prompts import index_prompt, planning_prompt, tools_prompt
from tools import edit_file, read_file

load_dotenv()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

console = Console()


def get_all_files(path: str, blacklist: set[str]) -> list[str]:
    total_files: list[str] = []

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in blacklist]

        for file in files:
            full_file_path = os.path.join(root, file)

            if file.startswith('.'):
                continue 

            if file in blacklist:
                continue

            file_extension = file.split('.')[-1]
            if file_extension in blacklist:
                continue

            total_files.append(full_file_path)
    return total_files


def create_index(project_path: str) -> None:
    console.print("create_index() called")
    files = get_all_files(project_path, blacklist={"node_modules", "__pycache__",".git", ".next", ".turbo", ".DS_Store", "svg", "lock", "package-lock.json", "ico", "hls", "png"})

    for file_path in files:
        print("---\n" + file_path + "\n---\n")
        with open(file_path) as f:
            content = read_file(file_path)

        response = client.responses.create(
            model="gpt-4.1",
            instructions="You are a coding agent",
            input=index_prompt(files, file_path, content),
        )

        print(response.output_text)

        with open("index", "a") as f:
            f.write(f"{file_path}\n{response.output_text}\n")



def plan(task: str) -> str:
    with open("index") as f:
        index_contents = f.read()

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{
            "role": "user",
            "content": planning_prompt(task, index_contents)
        }],
        stream=True
    )

    full_response = ""
    console.print(Panel("Planning Response", title="Planning Phase", style="bold blue"))

    for chunk in response:
        if chunk.choices[0].delta.content:
            content = chunk.choices[0].delta.content
            full_response += content
            console.print(content, end="", style="dim")

    console.print()
    return full_response


def extract_command(response: str) -> str | None:
    start = response.find("<terminal>")
    end = response.find("</terminal>")
    if start == -1 or end == -1:
        return None
    return response[start + len("<terminal>"):end].strip()


def run_command(command: str) -> str:
    try:
        return subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as e:
        return f"[ERROR]\n{e.output}"

def loop(messages: list[ChatCompletionMessageParam]) -> list[ChatCompletionMessageParam]:
    system_prompt: ChatCompletionMessageParam = {"role": "system", "content": tools_prompt(os.getcwd())}
    while True:
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[system_prompt] + messages
        )
        content = response.choices[0].message.content
        if not content:
            console.print("[bold red]No response from GPT.[/bold red]")
            break
        console.rule("[bold blue]Assistant Response[/bold blue]")
        console.print(Markdown(content))


        if "<thinking>" in content and "</thinking>" in content:
            thinking = content.split("<thinking>")[1].split("</thinking>")[0].strip()
            console.print(Panel(thinking, title="Thinking", style="dim italic"))


        if "<read_file>" in content and "</read_file>" in content:
            file_path = content.split("<read_file>")[1].split("</read_file>")[0].strip()
            console.print(Panel(f"Reading file: {file_path}", title="Tool Use: read_file", style="cyan"))
            try:
                file_content = read_file(file_path)
                console.print(Panel(file_content, title="File Content", border_style="blue"))

                messages.append({
                    "role": "user", 
                    "content": f"<file_content>{file_content}</file_content>"
                })
                continue
            except Exception as e:
                error_msg = f"[ERROR] Could not read file: {str(e)}"
                console.print(Panel(error_msg, title="File Read Error", border_style="red"))
                messages.append({
                    "role": "user",
                    "content": f"<file_content>{error_msg}</file_content>"
                })
                continue


        if "<edit_file>" in content and "</edit_file>" in content:
            edit_content = content.split('<edit_file>')[1].split('</edit_file>')[0].strip()
            console.print(Panel(f"Editing file with:\n{edit_content}", title="Tool Use: edit_file", style="yellow"))
            try:

                file_path_marker = 'file_path:'
                old_text_marker = 'old_text:'
                new_text_marker = 'new_text:'

                file_path_start = edit_content.find(file_path_marker)
                old_text_start = edit_content.find(old_text_marker)
                if file_path_start == -1 or old_text_start == -1:
                    raise ValueError("Missing file_path or old_text parameter")
                file_path = edit_content[file_path_start + len(file_path_marker):old_text_start].strip()

                new_text_start = edit_content.find(new_text_marker)
                if new_text_start == -1:
                    raise ValueError("Missing new_text parameter")
                old_text = edit_content[old_text_start + len(old_text_marker):new_text_start].strip()

                new_text = edit_content[new_text_start + len(new_text_marker):].strip()

                result = edit_file(file_path, old_text, new_text)
                console.print(Panel(result, title="Edit Result", border_style="green"))

                messages.append({
                    "role": "user",
                    "content": f"<edit_result>{result}</edit_result>"
                })
                continue
            except Exception as e:
                error_msg = f"[ERROR] Could not edit file: {str(e)}"
                console.print(Panel(error_msg, title="File Edit Error", border_style="red"))
                messages.append({
                    "role": "user",
                    "content": f"<edit_result>{error_msg}</edit_result>"
                })
                continue

        if "<terminal>" in content and "</terminal>" in content:
            command = content.split("<terminal>")[1].split("</terminal>")[0].strip()
            console.print(Panel.fit(Syntax(command, "bash", theme="monokai", line_numbers=False), title="Executing Command"))
            try:
                result = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT, text=True)
            except subprocess.CalledProcessError as e:
                result = f"[ERROR]\n{e.output}"
            if len(result) > 10000:
                result = "[ERROR] Output too large, pick commands whose output won't be this large to fit into context window"
            console.print(Panel(result.strip(), title="Command Output", border_style="green"))
            messages.append({
                "role": "user",
                "content": f"<output>{result}</output>"
            })
            continue

        console.print("[bold yellow]No tool commands found. Loop stopping.[/bold yellow]")
        break

    return messages

class PolluxApp(App[Any]):
    CSS = '''
    Screen {
        align: center middle;
    }
    '''

    def compose(self) -> ComposeResult:
        yield Static("Enter your name")
        yield Input(placeholder="Your name")

    def on_input_submitted(self, event: Input.Submitted):
        self.exit(f"You typed this dawg: {event.value}")


if __name__ == "__main__":
    task = Prompt.ask("prompt")

    plan_response = plan(task)

    messages: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": task},
        {"role": "assistant", "content": plan_response}
    ]

    while True:
        messages.append(
            {"role": "user", "content": user_msg}
        )
        messages = loop(messages)
        user_msg = Prompt.ask("prompt")
