import os

from rich.console import Console
from globals import MODEL, client
from prompts import index_prompt
from tools import read_file
from utils import llm_completion

console = Console()

def get_all_files(path: str, blacklist: set[str]) -> list[str]:
    total_files = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in blacklist]
        for file in files:
            if file.startswith('.') or file in blacklist:
                continue
            ext = file.split('.')[-1]
            if ext in blacklist:
                continue
            total_files.append(os.path.join(root, file))
    return total_files


def index_single_file(file_path: str, all_files: list[str]) -> str:
    content = read_file(file_path)
    response = llm_completion(
        prompt=index_prompt(all_files, file_path, content),
        client=client,
        model=MODEL,
        console=console,
        retries=3
    )
    return response
def create_index(project_path: str) -> None:
    console.print("create_index() called")
    files = get_all_files(project_path, {
        "node_modules", "__pycache__", ".git", ".next", ".turbo", ".DS_Store",
        "svg", "lock", "package-lock.json", "ico", "hls", "png"
    })
    for file_path in files:
        console.print(f"\n---\n{file_path}\n---\n")
        indexed_text = index_single_file(file_path, files)
        console.print(indexed_text)
        with open("index", "a") as f:
            f.write(f"{file_path}\n{indexed_text}\n")
