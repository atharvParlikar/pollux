from pathlib import Path
import sys

def read_file(file_path: str) -> str:
    try:
        content = Path(file_path).read_text(encoding='utf-8')
        if len(content) > 50000:
            return content[:50000] + f"\n\n[TRUNCATED - File is {len(content)} characters, showing first 50,000]"
        return content
    except FileNotFoundError:
        return f"[ERROR] File not found: {file_path}"
    except PermissionError:
        return f"[ERROR] Permission denied: Cannot read {file_path}"
    except UnicodeDecodeError:
        return f"[ERROR] Cannot read file {file_path}: File appears to be binary or uses unsupported encoding"
    except Exception as e:
        return f"[ERROR] Unexpected error reading {file_path}: {str(e)}"

def digit_count(x: int) -> int:
    return len(str(x))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("[ERROR] Usage: python read_file.py <file_path>")
        sys.exit(1)

    file_path = sys.argv[1]
    result = read_file(file_path)
    lines = result.split('\n')

    max_padding = digit_count(len(lines) + 1)

    new_result = ''
    for (i, line) in enumerate(lines):
        new_result += f"{i + 1}" + (max_padding - digit_count(i + 1)) * ' ' + " | " + line + "\n"

    print(new_result)
