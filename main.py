# pyright: reportUnusedCallResult=false

import os
import subprocess
import sys
import time
import re
import yaml
from dotenv import load_dotenv
import json
from openai import OpenAI
from typing import Any
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared.chat_model import ChatModel
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.syntax import Syntax
import logging
from pathlib import Path

from prompts import decision_router_prompt_template, insert_context_prompt
from utils import extract_tag

PROJECT_DIR = "/Users/atharvparlikar/dev/pollux-py"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()
console = Console()

MODEL: ChatModel = "gpt-4.1"
MAX_RETRIES = 3
RETRY_DELAY = 1.0
COMMAND_TIMEOUT = 30
MAX_CONTEXT_LENGTH = 10000
MAX_HISTORY_LENGTH = 50

class AgentError(Exception):
    """Base exception for agent errors"""
    pass

class ToolCallError(AgentError):
    """Error in tool execution"""
    pass

class LLMError(AgentError):
    """Error in LLM completion"""
    pass

class Agent:
    def __init__(self, client: OpenAI) -> None:
        self.current_prompt: str = ""
        self.plan: str = ""
        self.goal: str = ""
        self.context: str = ""
        self.history: list[dict[str, Any]] = []
        self.tool_outputs: list[str] = []
        self.tools_str: str = ""
        self.model: ChatModel = MODEL
        self.client: OpenAI = client
        self.max_iterations: int = 30  # Prevent infinite loops
        self.iteration_count: int = 0

        self._load_tools()
        self._validate_environment()


    def _load_tools(self) -> None:
        """Load tools configuration with proper error handling"""
        tools_path = Path('./tools.yaml')
        try:
            if not tools_path.exists():
                raise FileNotFoundError(f"tools.yaml not found at {tools_path}")

            with open(tools_path, 'r', encoding='utf-8') as f:
                self.tools_str = f.read()
            if not self.tools_str.strip():
                raise ValueError("tools.yaml is empty")

            logger.info("Successfully loaded tools configuration")
        except (FileNotFoundError, ValueError) as e:
            console.log(f"[bold red]Error loading tools: {e}[/]")
            logger.error(f"Failed to load tools: {e}")
            sys.exit(1)
        except Exception as e:
            console.log(f"[bold red]Unexpected error loading tools: {e}[/]")
            logger.error(f"Unexpected error loading tools: {e}")
            sys.exit(1)

    def _validate_environment(self) -> None:
        """Validate required environment variables and dependencies"""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            console.log("[bold red]OPENAI_API_KEY environment variable not set[/]")
            logger.error("OPENAI_API_KEY not found in environment")
            sys.exit(1)

        try:
            # Test OpenAI client
            self.client.models.list()
            logger.info("OpenAI client validated successfully")
        except Exception as e:
            console.log(f"[bold red]Failed to validate OpenAI client: {e}[/]")
            logger.error(f"OpenAI client validation failed: {e}")
            sys.exit(1)

    def prompt(self, prompt: str) -> None:
        """Set the current prompt with validation"""
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")
        self.current_prompt = prompt.strip()
        logger.info(f"Prompt set: {self.current_prompt[:100]}...")

    def llm_completion(self, prompt: str, retries: int = MAX_RETRIES) -> str:
        """LLM completion with retry logic and error handling"""
        if not prompt or not prompt.strip():
            raise LLMError("Prompt cannot be empty")

        prompt_: ChatCompletionMessageParam = {
            "role": "user",
            "content": prompt
        }

        for attempt in range(retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model, 
                    messages=[prompt_],
                    timeout=30,  # Add timeout
                    max_tokens=2000  # Limit response length
                )

                response_str = response.choices[0].message.content
                if not response_str:
                    raise LLMError("Empty response from LLM")

                logger.info(f"LLM completion successful on attempt {attempt + 1}")
                return response_str

            except Exception as e:
                logger.warning(f"LLM completion attempt {attempt + 1} failed: {e}")
                if attempt < retries - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff
                else:
                    raise LLMError(f"Failed to get LLM completion after {retries} attempts: {e}")

        print("Can't get LLM response, quitting...")
        exit(1)

    def decision_router(self) -> None:
        """Route decisions with iteration limits and error handling"""
        self.iteration_count += 1

        if self.iteration_count > self.max_iterations:
            console.log("[bold red]Maximum iteration limit reached. Stopping to prevent infinite loop.[/]")
            logger.error("Maximum iteration limit reached")
            return

        console.rule(f"[bold yellow]🤔 Agent is Thinking (Iteration {self.iteration_count})[/bold yellow]")

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
            console.print(Panel.fit(decision, title="🧠 LLM Decision", border_style="blue"))

            if not (("<toolcall>" in decision and "</toolcall>" in decision) or ("<command>" in decision and "</command>" in decision)):
                console.log("[yellow]No toolcall found in decision. Task may be complete or require human intervention.[/]")
                logger.info("No toolcall found in decision")
                return

            tool_str = extract_tag(tag="toolcall", text=decision)
            command_str = extract_tag(tag="command", text=decision)

            if len(tool_str) == 0 and len(command_str) == 0:
                console.log("[red]Failed to extract toolcall content[/]")
                logger.error("Failed to extract toolcall content")
                return

            print('tool_str', tool_str)
            print('command_str', command_str)

            if len(tool_str) > 0:
                self.tool_router_native(tool_str)

            if len(command_str) > 0:
                self.tool_router_external(command_str)

        except Exception as e:
            console.log(f"[bold red]Error in decision router: {e}[/]")
            logger.error(f"Decision router error: {e}")
            # Don't exit, try to continue

    def tool_router_native(self, tool_str: str) -> str | None:
        try:
            toolcall = json.loads(tool_str)
        except json.JSONDecodeError as e:
            console.print(f"[bold red]❌ Failed to parse toolcall JSON: {e}[/]")
            logger.error(f"JSON decode error: {e}")
            return None

        # Validate toolcall structure
        if not isinstance(toolcall, dict):
            console.print("[bold red]❌ Toolcall must be a dictionary[/]")
            logger.error("Invalid toolcall structure")
            return None

        tool = toolcall.get("tool")
        if not tool:
            console.print("[bold red]❌ No tool specified in toolcall[/]")
            logger.error("No tool specified")
            return None

        # Manage history size
        if len(self.history) >= MAX_HISTORY_LENGTH:
            self.history = self.history[-MAX_HISTORY_LENGTH//2:]
            logger.info("Truncated history to prevent memory issues")

        self.history.append(toolcall)
        logger.info(f"Executing tool: {tool}")

        console.rule(f"[bold green]🛠️ Tool Called: [cyan]{tool}[/cyan][/bold green]")
        console.print(Panel.fit(json.dumps(toolcall, indent=2), title="🔧 Toolcall Input", border_style="green"))

        try:
            if tool == "run_terminal":
                self._handle_terminal_tool(toolcall)
            elif tool == "create_plan":
                self._handle_plan_tool(toolcall)
            elif tool == "goal_reached":
                console.print("[bold green]✅ Goal reached successfully![/]")
                logger.info("Goal reached")
                return "goal_reached"
            else:
                console.print(f"[bold red]❌ Unknown tool: {tool}[/]")
                logger.error(f"Unknown tool: {tool}")

        except Exception as e:
            console.print(f"[bold red]❌ Error executing tool {tool}: {e}[/]")
            logger.error(f"Tool execution error: {e}")

        return None

    def tool_router_external(self, command: str):
        toolname = command.split(" ")[0]
        tools = yaml.safe_load(self.tools_str)

        tool = tools[toolname]
        tool_runner = tool["exec"]

        self.history.append({
            "type": "external_tool",
            "command": command
        })

        print("tool-runner: ", tool_runner)
        console.rule(f"[bold green]🛠️ tool use [cyan]{toolname}[/cyan] [/bold green]")

        result: str = ''

        if tool_runner == "python3":
            result = subprocess.check_output(
                f"python3 {PROJECT_DIR}/tools/{toolname}.py {command[len(toolname) + len(' '):]}",
                shell=True,
                stderr=subprocess.STDOUT,
                text=True
            )

        elif tool_runner == "binary":
            result = subprocess.check_output(
                f"{PROJECT_DIR}/tools/{toolname} {command[len(tool) + len(' '):]}",
                shell=True,
                stderr=subprocess.STDOUT,
                text=True
            )


        console.print(Panel.fit(result, title="tool output", border_style="cyan"))

        self.tool_outputs.append(result)

        self.insert_context(result)

    def _handle_terminal_tool(self, toolcall: dict[str, Any]) -> None:
        """Handle terminal tool execution with safety checks"""
        params = toolcall.get("params", {})
        command = params.get("command")

        if not command:
            raise ToolCallError("No command specified for terminal tool")

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
            raise ToolCallError(f"Dangerous command blocked: {command}")

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

            self.tool_outputs.append(toolcall_result)

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

        self.insert_context(new_context=toolcall_result)

    def _handle_plan_tool(self, toolcall: dict[str, Any]) -> None:
        """Handle plan creation tool"""
        params = toolcall.get("params", {})
        title = params.get("title", "Untitled Plan")
        steps = params.get("steps", "No steps provided")

        self.plan = f"{title}\n\n{steps}"
        logger.info(f"Plan created: {title}")

        console.print(Panel.fit(self.plan, title="🧭 New Plan", border_style="cyan"))
        self.decision_router()

    def insert_context(self, new_context: str) -> None:
        """Insert context with length management and error handling"""
        if not new_context:
            logger.warning("Empty context provided")
            return

        console.rule("[bold cyan]📥 Updating Context[/bold cyan]")

        try:
            if not self.history:
                logger.warning("No history available for context update")
                return

            updated_context = self.llm_completion(insert_context_prompt(
                old_context=self.context,
                new_context=new_context,
                toolcall=json.dumps(self.history[-1]),
                plan=self.plan
            ))

            extracted_context = extract_tag(tag="context", text=updated_context)
            if extracted_context:
                # Manage context length
                if len(extracted_context) > MAX_CONTEXT_LENGTH:
                    extracted_context = extracted_context[-MAX_CONTEXT_LENGTH:]
                    logger.info("Context truncated to prevent memory issues")

                self.context = extracted_context
                logger.info("Context updated successfully")
            else:
                logger.warning("Failed to extract context from LLM response")
                # Keep old context instead of clearing it

        except Exception as e:
            console.log(f"[bold red]Error updating context: {e}[/]")
            logger.error(f"Context update error: {e}")
            # Continue with old context

        console.print(Panel.fit(self.context, title="🧠 Updated Context", border_style="yellow"))
        self.decision_router()

    def run(self, task: str) -> None:
        """Main execution method with comprehensive error handling"""
        try:
            self.prompt(task)
            logger.info(f"Starting agent with task: {task}")
            self.decision_router()

        except KeyboardInterrupt:
            console.print("\n[bold yellow]⚠️ Agent interrupted by user[/]")
            logger.info("Agent interrupted by user")
        except Exception as e:
            console.print(f"[bold red]💥 Fatal error: {e}[/]")
            logger.error(f"Fatal error: {e}")
            sys.exit(1)
        finally:
            logger.info("Agent execution completed")


def main():
    """Main entry point with error handling"""
    try:
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        agent = Agent(client)

        task = Prompt.ask("[bold cyan]Enter your prompt[/bold cyan]")
        if not task.strip():
            console.print("[bold red]Empty task provided. Exiting.[/]")
            return

        agent.run(task)

    except KeyboardInterrupt:
        console.print("\n[bold yellow]Goodbye![/]")
    except Exception as e:
        console.print(f"[bold red]Failed to start agent: {e}[/]")
        logger.error(f"Startup error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
