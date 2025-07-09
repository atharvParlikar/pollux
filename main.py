# pyright: reportUnusedCallResult=false

import os
import subprocess
from typing import Any
from dotenv import load_dotenv
import json
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared.chat_model import ChatModel
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.syntax import Syntax

from prompts import decision_router_prompt_template, insert_context_prompt
from utils import extract_tag

# Load environment
load_dotenv()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
console = Console()

MODEL: ChatModel = "gpt-4.1"

class Agent:
    def __init__(self, client: OpenAI) -> None:
        self.current_prompt: str = ""
        self.plan: str = ""
        self.goal: str = ""
        self.context: str = ""
        self.history: list[dict[str, Any]] = []
        self.tools: str = ""

        try:
            with open('./tools.yaml') as f:
                self.tools = f.read()
        except FileNotFoundError:
            console.log("[bold red]tools.yaml file not found. Exiting...[/]")
            exit(1)

        self.model: ChatModel = MODEL
        self.client: OpenAI = client

    def prompt(self, prompt: str) -> None:
        self.current_prompt = prompt

    def llm_completion(self, prompt: str) -> str:
        prompt_: ChatCompletionMessageParam = {
            "role": "user",
            "content": prompt
        }
        response = self.client.chat.completions.create(model=self.model, messages=[prompt_])
        response_str = response.choices[0].message.content
        return response_str or "[ERROR] Could not generate response"

    def decision_router(self):
        console.rule("[bold yellow]🤔 Agent is Thinking[/bold yellow]")
        prompt = decision_router_prompt_template(
            prompt=self.current_prompt,
            plan=self.plan,
            goal=self.goal,
            context=self.context,
            history=self.history,
            tools=self.tools
        )
        decision = self.llm_completion(prompt)

        console.print(Panel.fit(decision, title="🧠 LLM Decision", border_style="blue"))

        if "<toolcall>" not in decision or "</toolcall>" not in decision:
            console.log("[red]No toolcall found in decision. Exiting...[/]")
            return

        tool_str = extract_tag(tag="toolcall", text=decision)
        self.tool_router(tool_str)

    def tool_router(self, tool_str: str) -> str | None:
        try:
            toolcall = json.loads(tool_str)
        except json.JSONDecodeError:
            console.print("[bold red]❌ Failed to parse toolcall JSON[/]")
            return

        self.history.append(toolcall)
        tool = toolcall.get("tool")
        toolcall_result: str = ""

        console.rule(f"[bold green]🛠️ Tool Called: [cyan]{tool}[/cyan][/bold green]")
        console.print(Panel.fit(json.dumps(toolcall, indent=2), title="🔧 Toolcall Input", border_style="green"))

        if tool == "run_terminal":
            command = toolcall["params"]["command"]
            try:
                toolcall_result = subprocess.check_output(
                    command, shell=True, stderr=subprocess.STDOUT, text=True
                )
            except subprocess.CalledProcessError as e:
                toolcall_result = f"[Command Failed]\n{e.output}"
            except subprocess.TimeoutExpired:
                toolcall_result = "[Timeout] Command took too long to execute"

            console.print(Panel.fit(
                Syntax(toolcall_result, "bash"),
                title="💻 Terminal Output",
                border_style="magenta"
            ))

            self.insert_context(new_context=toolcall_result)

        elif tool == "create_plan":
            title = toolcall["params"]["title"]
            steps = toolcall["params"]["steps"]
            self.plan = f"{title}\n\n{steps}"
            console.print(Panel.fit(self.plan, title="🧭 New Plan", border_style="cyan"))
            self.decision_router()

        elif tool == "goal_reached":
            return

    def insert_context(self, new_context: str):
        console.rule("[bold cyan]📥 Updating Context[/bold cyan]")

        updated_context = self.llm_completion(insert_context_prompt(
            old_context=self.context,
            new_context=new_context,
            toolcall=json.dumps(self.history[-1])
        ))

        self.context = extract_tag(tag="context", text=updated_context)

        console.print(Panel.fit(self.context, title="🧠 Updated Context", border_style="yellow"))
        self.decision_router()


if __name__ == "__main__":
    agent = Agent(client)
    task = Prompt.ask("[bold cyan]Enter your prompt[/bold cyan]")
    agent.prompt(task)
    agent.decision_router()

