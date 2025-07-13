# pyright: reportUnusedCallResult=false

import os
import subprocess
import sys
from openai import OpenAI
import yaml
from dotenv import load_dotenv
import json
from typing import Any
from rich.prompt import Prompt
from pathlib import Path

from agent_display import AgentDisplay
from globals import MAX_CONTEXT_LENGTH, MAX_HISTORY_LENGTH, MAX_RETRIES, MODEL, PROJECT_DIR, RETRY_DELAY, client
from native_tools import edit_file, handle_terminal_tool
from prompts import decision_router_prompt_template, insert_context_prompt
from utils import extract_tag, get_unified_diff

load_dotenv()


class Agent:
    def __init__(self, client: OpenAI):
        self.current_prompt = ""
        self.plan = ""
        self.goal = ""
        self.context = ""
        self.history = []
        self.tool_outputs = []
        self.tools_str = ""
        self.model = MODEL
        self.client = client
        self.max_iterations = 30
        self.iteration_count = 0
        self.display = AgentDisplay()

        self._load_tools()
        self._validate_environment()

    def _load_tools(self):
        tools_path = Path('./tools.yaml')
        try:
            if not tools_path.exists():
                raise FileNotFoundError(f"tools.yaml not found at {tools_path}")

            with open(tools_path, 'r', encoding='utf-8') as f:
                self.tools_str = f.read()

            if not self.tools_str.strip():
                raise ValueError("tools.yaml is empty")

        except Exception as e:
            self.display.error(f"Failed to load tools: {e}")
            sys.exit(1)

    def _validate_environment(self):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            self.display.error("OPENAI_API_KEY environment variable not set")
            sys.exit(1)

        try:
            self.client.models.list()
        except Exception as e:
            self.display.error(f"OpenAI client validation failed: {e}")
            sys.exit(1)

    def prompt(self, prompt: str):
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")
        self.current_prompt = prompt.strip()

    def llm_completion(self, prompt: str, retries: int = MAX_RETRIES) -> str:
        from utils import llm_completion
        return llm_completion(
            prompt=prompt,
            client=self.client,
            model=self.model,
            console=None,  # Disable console output from utils
            retries=retries,
            retry_delay=RETRY_DELAY
        )

    def _extract_thinking(self, decision: str) -> str:
        """Extract thinking content from decision"""
        thinking_patterns = ["thinking", "analysis", "plan", "reasoning"]

        for pattern in thinking_patterns:
            if f"<{pattern}>" in decision and f"</{pattern}>" in decision:
                thinking = extract_tag(tag=pattern, text=decision)
                if thinking:
                    return thinking
        return ""

    def _get_tool_display_info(self, tool_json: dict[str, Any]) -> tuple[str, str]:
        """Get display information for a tool"""
        tool_name = tool_json.get("tool", "unknown")
        params = tool_json.get("params", {})

        if tool_name == "edit_file":
            file_path = params.get("file_path", "")
            return tool_name, f"editing {file_path}"
        elif tool_name == "run_terminal":
            cmd = params.get("command", "")
            return tool_name, f"running: {cmd}"
        elif tool_name == "ask_human":
            question = params.get("question", "")
            return tool_name, f"asking: {question}"
        else:
            return tool_name, ""

    def decision_router(self):
        self.iteration_count += 1

        if self.iteration_count > self.max_iterations:
            self.display.error("Maximum iteration limit reached")
            return

        self.display.step_start()

        try:
            prompt = decision_router_prompt_template(
                prompt=self.current_prompt,
                plan=self.plan,
                goal=self.goal,
                context=self.context,
                history=self.history,
                toolcall_history=self.tool_outputs,
                tools=self.tools_str
            )

            decision = self.llm_completion(prompt)

            # Show thinking
            thinking = self._extract_thinking(decision)
            self.display.thinking(thinking)

            # Show action
            if "<toolcall>" in decision:
                tool_part = extract_tag(tag="toolcall", text=decision)
                if tool_part:
                    try:
                        tool_json = json.loads(tool_part)
                        tool_name, details = self._get_tool_display_info(tool_json)
                        self.display.tool_action(tool_name, details)
                    except:
                        self.display.tool_action("unknown tool")

            if "<command>" in decision:
                cmd_part = extract_tag(tag="command", text=decision)
                if cmd_part:
                    self.display.command_action(cmd_part)
            #
            # Execute tools
            tool_str = extract_tag(tag="toolcall", text=decision)
            command_str = extract_tag(tag="command", text=decision)

            if not tool_str and not command_str:
                self.display.task_complete("Task complete or waiting for input")
                return

            if tool_str:
                self.tool_router_native(tool_str)

            if command_str:
                self.tool_router_external(command_str)

        except Exception as e:
            self.display.error(f"Decision router error: {e}")

    def tool_router_native(self, tool_str: str):
        try:
            toolcall = json.loads(tool_str)
        except json.JSONDecodeError as e:
            self.display.error(f"Failed to parse toolcall JSON: {e}")
            return

        if not isinstance(toolcall, dict) or not toolcall.get("tool"):
            self.display.error("Invalid toolcall structure")
            return

        # Manage history size
        if len(self.history) >= MAX_HISTORY_LENGTH:
            self.history = self.history[-MAX_HISTORY_LENGTH//2:]

        self.history.append(toolcall)
        tool = toolcall["tool"]

        if tool == "run_terminal":
            result = handle_terminal_tool(toolcall)
            self.tool_outputs.append(result)
            self.display.tool_result(result)
            self.decision_router()

        elif tool == "edit_file":
            self._handle_edit_file(toolcall)

        elif tool == "ask_human":
            self._handle_ask_human(toolcall)

        elif tool == "create_plan":
            self._handle_create_plan(toolcall)

        elif tool == "goal_reached":
            message = toolcall.get('params', {}).get('message', 'Goal reached!')
            self.display.task_complete(message)

        else:
            self.display.error(f"Unknown tool: {tool}")

    def _handle_edit_file(self, toolcall: dict[str, Any]):
        params = toolcall["params"]
        file_path = params["file_path"]
        start_line = params["start_line"]
        end_line = params["end_line"]
        new_content = params["new_content"]

        try:
            with open(file_path) as f:
                current_content = f.read()

            result = edit_file(file_path=file_path, start_line=start_line, end_line=end_line, new_content=new_content)
            diff = get_unified_diff(old_content=current_content, new_content=result, filename=file_path.split("/")[-1])

            self.display.file_diff(diff)
            self.insert_context(diff)

        except Exception as e:
            error_message = str(e)
            self.display.error(f"Edit failed: {error_message}")
            self.insert_context(f"[ERROR] {error_message}")

    def _handle_ask_human(self, toolcall: dict[str, Any]):
        question = toolcall.get("params", {}).get("question", "")
        user_input = self.display.user_input_prompt(question)
        self.display.user_input_received(user_input)
        self.insert_context(f"User input: {user_input}")

    def _handle_create_plan(self, toolcall: dict[str, Any]):
        params = toolcall.get("params", {})
        title = params.get("title", "Untitled Plan")
        steps = params.get("steps", "No steps provided")

        self.plan = f"{title}\n\n{steps}"
        self.display.plan_created(title, steps)
        self.decision_router()

    def tool_router_external(self, command: str):
        toolname = command.split(" ")[0]
        tools = yaml.safe_load(self.tools_str)

        if toolname not in tools:
            self.display.error(f"Unknown external tool: {toolname}")
            return

        tool = tools[toolname]
        tool_runner = tool["exec"]

        self.history.append({
            "type": "external_tool",
            "command": command
        })

        try:
            if tool_runner == "python3":
                result = subprocess.check_output(
                    f"python3 {PROJECT_DIR}/external_tools/{toolname}.py {command[len(toolname) + 1:]}",
                    shell=True,
                    stderr=subprocess.STDOUT,
                    text=True
                )
            elif tool_runner == "binary":
                result = subprocess.check_output(
                    f"{PROJECT_DIR}/tools/{toolname} {command[len(toolname) + 1:]}",
                    shell=True,
                    stderr=subprocess.STDOUT,
                    text=True
                )
            else:
                self.display.error(f"Unknown tool runner: {tool_runner}")
                return

            self.display.tool_result(result)

            if toolname == "read_file":
                self._handle_read_file_result(command, result)

            self.insert_context(result)

        except subprocess.CalledProcessError as e:
            self.display.error(f"Tool execution failed: {e}")
            self.insert_context(f"[ERROR] {e}")

    def _handle_read_file_result(self, command: str, result: str):
        file_path = command.split(' ')[1] if len(command.split(' ')) > 1 else "unknown"
        # Remove existing file content from context
        self.context = '\n'.join(line for line in self.context.split('\n') 
                                if not line.startswith(f'=== File Content: {file_path} ==='))

        lines_count = len(result.split('\n'))
        self.display.tool_result(f"Read {lines_count} lines from {file_path}")
        self.context += f"\n\n=== File Content: {file_path} ===\n{result}"
        self.decision_router()

    def insert_context(self, new_context: str):
        if not new_context or not self.history:
            return

        try:
            updated_context = self.llm_completion(insert_context_prompt(
                old_context=self.context,
                new_context=new_context,
                toolcall=json.dumps(self.history[-1]),
                plan=self.plan
            ))

            extracted_context = extract_tag(tag="context", text=updated_context)
            if extracted_context:
                if len(extracted_context) > MAX_CONTEXT_LENGTH:
                    extracted_context = extracted_context[-MAX_CONTEXT_LENGTH:]

                self.context = extracted_context
                self.display.context_updated()

        except Exception as e:
            self.display.error(f"Context update error: {e}")

        self.decision_router()

    def run(self, task: str):
        try:
            self.prompt(task)
            self.display.task_start(task)
            self.decision_router()
        except KeyboardInterrupt:
            self.display.warning("Interrupted by user")
        except Exception as e:
            self.display.error(f"Fatal error: {e}")
            sys.exit(1)


def main():
    try:
        agent = Agent(client)

        task = Prompt.ask("[bold cyan]Enter your task[/bold cyan]")
        if not task.strip():
            print("Empty task provided. Exiting.")
            return

        agent.run(task)

    except KeyboardInterrupt:
        print("\nGoodbye!")
    except Exception as e:
        print(f"Failed to start agent: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
