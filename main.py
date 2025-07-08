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

from prompts import decision_router_prompt_template, insert_context_prompt

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
        except:
            print("tools.yaml file not found quitting...")
            exit(1)

        self.model: ChatModel = "gpt-4.1"
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

        if response_str is not None:
            return response_str
        else:
            return "SOMETHING WENT WRONG: COULD NOT CREATE CHAT COMPLETION"

    def decision_router(self):
        prompt = decision_router_prompt_template(
            prompt=self.current_prompt,
            plan=self.plan,
            goal=self.goal,
            context=self.context,
            history=self.history,
            tools=self.tools
        )

        decision = self.llm_completion(prompt)
        print(decision)
        tool_str = decision[decision.find("<toolcall>") + len("<toolcall>"): decision.find("</toolcall>")]
        self.tool_router(tool_str)

    def tool_router(self, tool_str: str) -> str | None:
        toolcall: dict[str, Any] = {}
        try:
            toolcall = json.loads(tool_str)
        except:
            return "[ERROR] error parsing toolcall"

        self.history.append(toolcall)

        tool = toolcall["tool"]
        toolcall_result: str = ''
        if tool == "terminal":
            command: str = toolcall["params"]["command"]
            timeout: int = toolcall["params"]["timeout"]
            toolcall_result = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT, text=True, timeout=timeout)
            self.insert_context(new_context=toolcall_result)

        if tool == "plan":
            title = toolcall["params"]["title"]
            steps = toolcall["params"]["steps"]
            self.plan = f"{title}\n\n{steps}"

        self.decision_router()

    def insert_context(self, new_context: str):
        new_context = self.llm_completion(insert_context_prompt(
            old_context=self.context,
            new_context=new_context,
            toolcall=json.dumps(self.history[-1])
        ))

        self.context = new_context
        print(f"=== New Context ===\n{new_context}")

        self.decision_router()


if __name__ == "__main__":
    agent = Agent(client)
    task = Prompt.ask("prompt")
    agent.prompt(task)
    agent.decision_router()

