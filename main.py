# pyright: reportUnusedCallResult=false

import os
import subprocess
from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from tqdm import tqdm
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown

from prompts import index_prompt, planning_prompt, tools_prompt

load_dotenv()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

console = Console()


def get_all_files(path: str, blacklist: set[str]) -> list[str]:
    total_files: list[str] = []

    for root, dirs, files in os.walk(path):
        # Filter directories in-place for os.walk to skip them
        dirs[:] = [d for d in dirs if d not in blacklist]

        for file in files:
            # Get the full path of the current file
            full_file_path = os.path.join(root, file)

            # Check for dotfiles
            if file.startswith('.'):
                continue # Skip hidden files

            # Check if the full filename is in the blacklist
            if file in blacklist:
                continue

            # Check if the file extension is in the blacklist
            file_extension = file.split('.')[-1]
            if file_extension in blacklist:
                continue

            total_files.append(full_file_path)
    return total_files


def create_index(project_path: str) -> None:
    files = get_all_files(project_path, blacklist={"node_modules", ".git", ".next", ".turbo", ".DS_Store", "svg", "lock", "package-lock.json", "ico", "hls", "png"})

    for file in files:
        print("---\n" + file + "\n---\n")
        with open(file) as f:
            content = f.read()

        response = client.responses.create(
            model="gpt-4.1",
            instructions="You are a coding agent",
            input=index_prompt(files, file, content),
        )

        print(response.output_text)

        with open("index", "a") as f:
            f.write(f"{file}\n{response.output_text}\n")



def plan(task: str) -> None:
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

    for chunk in response:
        print(chunk.choices[0].delta.content, end="")


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


def loop(messages: list[ChatCompletionMessageParam]) -> None:
    system_prompt: ChatCompletionMessageParam = {"role": "system", "content": tools_prompt()}

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

        # Show <thinking> block if present
        if "<thinking>" in content and "</thinking>" in content:
            thinking = content.split("<thinking>")[1].split("</thinking>")[0].strip()
            console.print(Panel(thinking, title="Thinking", style="dim italic"))

        # Extract command from <terminal>
        if "<terminal>" not in content or "</terminal>" not in content:
            console.print("[bold yellow]No <terminal> command found. Loop stopping.[/bold yellow]")
            break

        command = content.split("<terminal>")[1].split("</terminal>")[0].strip()
        console.print(Panel.fit(Syntax(command, "bash", theme="monokai", line_numbers=False), title="Executing Command"))

        # Run command
        try:
            result = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT, text=True)
        except subprocess.CalledProcessError as e:
            result = f"[ERROR]\n{e.output}"

        console.print(Panel(result.strip(), title="Command Output", border_style="green"))

        # Feed output back into loop
        messages.append({
            "role": "user",
            "content": f"<output>{result}</output>"
        })


if __name__ == "__main__":
    # loop([
    #     {"role": "user", "content": "Download c spec, and put it in c_man directory in current dir"}
    # ])
    plan("Add a mute and camera off button for the people streaming / on video call")
