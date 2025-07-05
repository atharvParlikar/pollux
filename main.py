# pyright: reportUnusedCallResult=false

import os
from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from rich.console import Console
from rich.prompt import Prompt
from rich.markdown import Markdown

from prompts import tools_prompt
from tool_handlers import extract_thinking, handle_edit_file, handle_read_file, handle_terminal_command

load_dotenv()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

console = Console()


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
        extract_thinking(content)

        if handle_read_file(content, messages):
            continue
        if handle_edit_file(content, messages):
            continue
        if handle_terminal_command(content, messages):
            continue

        console.print("[bold yellow]No tool commands found. Loop stopping.[/bold yellow]")
        break

    return messages

if __name__ == "__main__":
    task = Prompt.ask("prompt")
    messages: list[ChatCompletionMessageParam] = [{"role": "user", "content": task}]

    while True:
        messages = loop(messages)
        user_msg = Prompt.ask("prompt")
        messages.append({"role": "user", "content": user_msg})
