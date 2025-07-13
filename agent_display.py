from rich.console import Console
from rich.prompt import Prompt


class AgentDisplay:
    """Centralized display system for agent output"""
    
    def __init__(self):
        self.console = Console()
        self.step_count = 0
    
    def task_start(self, task: str):
        self.console.print(f"[bold green]🚀 Task:[/bold green] {task}")
    
    def step_start(self):
        self.step_count += 1
        self.console.print(f"[dim]--- Step {self.step_count} ---[/dim]")
    
    def thinking(self, content: str):
        if content:
            self.console.print(f"[dim]💭 {content}[/dim]")
    
    def tool_action(self, tool_name: str, details: str = ""):
        if details:
            self.console.print(f"[cyan]🔧 {tool_name}: {details}[/cyan]")
        else:
            self.console.print(f"[cyan]🔧 {tool_name}[/cyan]")
    
    def command_action(self, command: str):
        self.console.print(f"[cyan]⚡ {command}[/cyan]")
    
    def tool_result(self, result: str):
        if result.strip():
            self.console.print(f"[dim]→ {result.strip()}[/dim]")
    
    def file_diff(self, diff: str):
        for line in diff.split('\n'):
            if line.startswith('+'):
                self.console.print(f'[green]{line}[/green]')
            elif line.startswith('-'):
                self.console.print(f'[red]{line}[/red]')
            else:
                self.console.print(line)
    
    def plan_created(self, title: str, steps: str):
        self.console.print(f"[cyan]📋 Plan: {title}[/cyan]")
        self.console.print(f"[dim]→ {steps}[/dim]")
    
    def context_updated(self):
        self.console.print("[dim]📝 Context updated[/dim]")
    
    def task_complete(self, message: str = "Task complete"):
        self.console.print(f"[bold green]✅ {message}[/]")
    
    def error(self, message: str):
        self.console.print(f"[bold red]❌ {message}[/]")
    
    def warning(self, message: str):
        self.console.print(f"[yellow]⚠️ {message}[/yellow]")
    
    def user_input_prompt(self, question: str) -> str:
        return Prompt.ask(f"[bold magenta]🤖 {question}[/bold magenta]")
    
    def user_input_received(self, input_text: str):
        self.console.print(f"[dim]→ User: {input_text}[/dim]")

