# tools/edit_file.py
from pathlib import Path
from rich.console import Console
import sys

console = Console()

def edit_file(file_path: str, start_line: int, end_line: int, new_content: str) -> str:
    """
    Edit a file by replacing lines from start_line to end_line (inclusive, 1-based) with new_content.

    Special cases:
    - To insert at line N: start_line = N, end_line = N-1 (replace 0 lines)
    - To append to end: start_line = -1, end_line = -1
    - To delete lines: start_line = N, end_line = M, new_content = ""
    - To replace lines: start_line = N, end_line = M, new_content = "replacement"
    """
    try:
        path = Path(file_path)

        # Handle file creation if it doesn't exist
        if not path.exists():
            if start_line == 1 and end_line == 0:
                # Creating new file with content
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(new_content, encoding='utf-8')
                return f"File created: {file_path}"
            else:
                return f"[ERROR] File not found: {file_path}"
        
        # Read existing content
        content = path.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        # Handle append to end
        if start_line == -1 and end_line == -1:
            lines.append(new_content)
            new_file_content = '\n'.join(lines)
            path.write_text(new_file_content, encoding='utf-8')
            return f"Content appended to {file_path}"
        
        # Validate line numbers
        if start_line < 1 or (end_line > 0 and end_line < start_line and not (start_line == end_line + 1)):
            return f"[ERROR] Invalid line numbers: start={start_line}, end={end_line}"
        
        # Handle insertion (start_line = N, end_line = N-1)
        if start_line == end_line + 1:
            # Insert at position start_line
            insert_pos = start_line - 1
            if insert_pos > len(lines):
                return f"[ERROR] Cannot insert at line {start_line}, file only has {len(lines)} lines"
            lines.insert(insert_pos, new_content)
            operation = f"Inserted content at line {start_line}"
        else:
            # Replace/delete lines
            if end_line == 0:
                end_line = start_line
            
            if start_line > len(lines) or end_line > len(lines):
                return f"[ERROR] Line numbers out of range. File has {len(lines)} lines"
            
            # Convert to 0-based indexing
            start_idx = start_line - 1
            end_idx = end_line
            
            # Replace the lines
            if new_content:
                lines[start_idx:end_idx] = [new_content]
                operation = f"Replaced lines {start_line}-{end_line}"
            else:
                del lines[start_idx:end_idx]
                operation = f"Deleted lines {start_line}-{end_line}"
        
        # Write back to file
        new_file_content = '\n'.join(lines)
        path.write_text(new_file_content, encoding='utf-8')
        
        return f"{operation} in {file_path}"
        
    except Exception as e:
        return f"[ERROR] Failed to edit file: {str(e)}"

def main():
    if len(sys.argv) != 5:
        console.print("[ERROR] Usage: python edit_file.py <file_path> <start_line> <end_line> <new_content>", style="bold red")
        console.print("\nExamples:", style="bold")
        console.print("  # Create new file:")
        console.print("  python edit_file.py 'file.txt' 1 0 'Hello World'")
        console.print("  # Insert at line 5:")
        console.print("  python edit_file.py 'file.txt' 5 4 'New line'")
        console.print("  # Replace lines 2-4:")
        console.print("  python edit_file.py 'file.txt' 2 4 'Replacement content'")
        console.print("  # Delete lines 3-5:")
        console.print("  python edit_file.py 'file.txt' 3 5 ''")
        console.print("  # Append to end:")
        console.print("  python edit_file.py 'file.txt' -1 -1 'End content'")
        sys.exit(1)
    
    file_path = sys.argv[1]
    start_line = int(sys.argv[2])
    end_line = int(sys.argv[3])
    new_content = sys.argv[4]
    
    result = edit_file(file_path, start_line, end_line, new_content)
    console.print(result)

if __name__ == "__main__":
    main()
