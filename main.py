# pyright: reportUnusedCallResult=false

import os
import subprocess
import sys
import yaml
from dotenv import load_dotenv
import json
from openai import OpenAI
from typing import Any
from openai.types.shared.chat_model import ChatModel
from rich.prompt import Prompt
from pathlib import Path

from globals import MAX_CONTEXT_LENGTH, MAX_HISTORY_LENGTH, MAX_RETRIES, MODEL, PROJECT_DIR, RETRY_DELAY, console, logger
from native_tools import edit_file, handle_terminal_tool
from prompts import decision_router_prompt_template, insert_context_prompt
from utils import extract_tag, get_unified_diff

# Load environment
load_dotenv()

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
        from utils import llm_completion
        return llm_completion(
            prompt=prompt,
            client=self.client,
            model=self.model,
            console=console,
            retries=retries,
            retry_delay=RETRY_DELAY
        )

    def _show_thinking(self, decision: str) -> None:
        """Show agent's thinking process in a clean way"""
        # Extract thinking section if it exists
        thinking_patterns = [
            ("thinking>", "thinking"),
            ("analysis>", "analysis"),
            ("plan>", "plan"),
            ("reasoning>", "reasoning")
        ]
        
        for pattern, tag in thinking_patterns:
            if f"<{pattern}" in decision and f"</{tag}>" in decision:
                thinking = extract_tag(tag=tag, text=decision)
                if thinking:
                    # Show first line or two of thinking
                    lines = thinking.strip().split('\n')
                    preview = lines[0]
                    if len(lines) > 1 and len(preview) < 60:
                        preview += f" {lines[1]}"
                    if len(preview) > 80:
                        preview = preview[:77] + "..."
                    console.print(f"[dim]💭 {preview}[/dim]")
                    break

    def decision_router(self) -> None:
        """Route decisions with iteration limits and error handling"""
        self.iteration_count += 1

        if self.iteration_count > self.max_iterations:
            console.log("[bold red]Maximum iteration limit reached. Stopping to prevent infinite loop.[/]")
            logger.error("Maximum iteration limit reached")
            return

        console.print(f"[dim]🤔 Step {self.iteration_count}[/dim]")

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
            
            # Show what the agent is thinking
            self._show_thinking(decision)

            # Show action being taken
            if "<toolcall>" in decision:
                tool_part = extract_tag(tag="toolcall", text=decision)
                if tool_part:
                    try:
                        tool_json = json.loads(tool_part)
                        tool_name = tool_json.get("tool", "unknown")
                        
                        # Show tool with relevant params
                        if tool_name == "edit_file":
                            file_path = tool_json.get("params", {}).get("file_path", "")
                            console.print(f"[cyan]🔧 Editing {file_path}[/cyan]")
                        elif tool_name == "run_terminal":
                            cmd = tool_json.get("params", {}).get("command", "")
                            console.print(f"[cyan]⚡ Running: {cmd}[/cyan]")
                        elif tool_name == "ask_human":
                            question = tool_json.get("params", {}).get("question", "")
                            console.print(f"[cyan]❓ Question: {question}[/cyan]")
                        else:
                            console.print(f"[cyan]🔧 Using {tool_name}[/cyan]")
                    except:
                        console.print("[cyan]🔧 Executing tool[/cyan]")

            if "<command>" in decision:
                cmd_part = extract_tag(tag="command", text=decision)
                if cmd_part:
                    console.print(f"[cyan]⚡ Command: {cmd_part}[/cyan]")

            if not (("<toolcall>" in decision and "</toolcall>" in decision) or ("<command>" in decision and "</command>" in decision)):
                console.log("[green]✅ Task complete or waiting for input[/]")
                logger.info("No toolcall found in decision")
                return

            tool_str = extract_tag(tag="toolcall", text=decision)
            command_str = extract_tag(tag="command", text=decision)

            if len(tool_str) == 0 and len(command_str) == 0:
                console.log("[red]Failed to extract toolcall content[/]")
                logger.error("Failed to extract toolcall content")
                return

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

        if tool == "run_terminal":
            result = handle_terminal_tool(toolcall)
            self.history.append(toolcall)
            self.tool_outputs.append(result)

            # Show terminal output
            if result.strip():
                lines = result.strip().split('\n')
                if len(lines) <= 10:
                    # Show all lines if reasonable
                    console.print(f"[dim]→ {result.strip()}[/dim]")
                else:
                    # Show first 8 lines for really long output
                    preview = '\n'.join(lines[:8])
                    console.print(f"[dim]→ {preview}[/dim]")
                    console.print(f"[dim]  ... ({len(lines)-8} more lines)[/dim]")

            self.decision_router()

        elif tool == "edit_file":
            params = toolcall["params"]

            file_path: str= params["file_path"]
            start_line: int = params["start_line"]
            end_line: int = params["end_line"]
            new_content: str = params["new_content"]

            self.history.append(toolcall)

            current_file_content = '' 

            with open(file_path) as f:
                current_file_content = f.read()

            try:
                result: str = edit_file(file_path=file_path, start_line=start_line, end_line=end_line, new_content=new_content)
                diff = get_unified_diff(old_content=current_file_content, new_content=result, filename=file_path.split("/")[-1])
                
                # Show edit details
                diff_lines = diff.split('\n')
                added_lines = len([line for line in diff_lines if line.startswith('+')])
                removed_lines = len([line for line in diff_lines if line.startswith('-')])
                console.print(f"[dim]→ +{added_lines} -{removed_lines} lines[/dim]")
                
                # Show the diff if it's not too long
                if len(diff_lines) <= 20:
                    console.print(f"[dim]{diff}[/dim]")
                elif len(diff_lines) <= 50:
                    # Show first part of diff
                    preview = '\n'.join(diff_lines[:15])
                    console.print(f"[dim]{preview}[/dim]")
                    console.print(f"[dim]... ({len(diff_lines)-15} more lines)[/dim]")
                else:
                    console.print(f"[dim]→ Large diff ({len(diff_lines)} lines)[/dim]")
                
                self.insert_context(diff)
            except Exception as e:
                error_message = str(e)
                console.print(f"[red]❌ Edit failed: {error_message}[/red]")
                self.insert_context(f"[ERROR] {error_message}")

        elif tool == "ask_human":
            question = toolcall.get("params", {}).get("question", "")
            user_input = Prompt.ask(f"[bold magenta]🤖 {question}[/bold magenta]")
            console.print(f"[dim]→ User said: {user_input}[/dim]")
            self.insert_context(f"User input: {user_input}")

        elif tool == "create_plan":
            self._handle_plan_tool(toolcall)

        elif tool == "goal_reached":
            console.print("[bold green]✅ Goal reached![/]")
            logger.info("Goal reached")
            return "goal_reached"
        else:
            console.print(f"[bold red]❌ Unknown tool: {tool}[/]")
            logger.error(f"Unknown tool: {tool}")

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

        result: str = ''

        if tool_runner == "python3":
            result = subprocess.check_output(
                f"python3 {PROJECT_DIR}/external_tools/{toolname}.py {command[len(toolname) + len(' '):]}",
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

        # Show output
        if result.strip():
            lines = result.strip().split('\n')
            if len(lines) <= 15:
                # Show full output if reasonable
                console.print(f"[dim]→ {result.strip()}[/dim]")
            else:
                # Show first 10 lines for really long output
                preview = '\n'.join(lines[:10])
                console.print(f"[dim]→ {preview}[/dim]")
                console.print(f"[dim]  ... ({len(lines)-10} more lines)[/dim]")

        if toolname == "read_file":
            file_path = command.split(' ')[1] if len(command.split(' ')) > 1 else "unknown"
            lines_count = len(result.split('\n'))
            console.print(f"[dim]→ Read {lines_count} lines from {file_path}[/dim]")
            self.context += f"\n\n=== File Content: {file_path} ===\n{result}"
            self.decision_router()

        self.insert_context(result)

    def _handle_plan_tool(self, toolcall: dict[str, Any]) -> None:
        """Handle plan creation tool"""
        params = toolcall.get("params", {})
        title = params.get("title", "Untitled Plan")
        steps = params.get("steps", "No steps provided")

        self.plan = f"{title}\n\n{steps}"
        logger.info(f"Plan created: {title}")

        # Show plan with full steps unless really long
        steps_lines = steps.split('\n')
        console.print(f"[cyan]📋 Plan: {title}[/cyan]")
        if len(steps_lines) <= 10:
            console.print(f"[dim]→ {steps}[/dim]")
        else:
            preview = '\n'.join(steps_lines[:8])
            console.print(f"[dim]→ {preview}[/dim]")
            console.print(f"[dim]  ... ({len(steps_lines)-8} more lines)[/dim]")
        self.decision_router()

    def insert_context(self, new_context: str) -> None:
        """Insert context with length management and error handling"""
        if not new_context:
            logger.warning("Empty context provided")
            return

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
                console.print("[dim]📝 Context updated[/dim]")
                logger.info("Context updated successfully")
            else:
                logger.warning("Failed to extract context from LLM response")
                # Keep old context instead of clearing it

        except Exception as e:
            console.log(f"[bold red]Error updating context: {e}[/]")
            logger.error(f"Context update error: {e}")
            # Continue with old context

        self.decision_router()

    def run(self, task: str) -> None:
        """Main execution method with comprehensive error handling"""
        try:
            self.prompt(task)
            console.print(f"[bold green]🚀 Starting task:[/bold green] {task}")
            logger.info(f"Starting agent with task: {task}")
            self.decision_router()

        except KeyboardInterrupt:
            console.print("\n[bold yellow]⚠️ Interrupted by user[/]")
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

        task = Prompt.ask("[bold cyan]Enter your task[/bold cyan]")
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
