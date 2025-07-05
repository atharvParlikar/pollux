from rich.console import Console, console
from rich.panel import Panel
from main import client
from prompts import planning_prompt

console = Console()

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
