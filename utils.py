import difflib

def extract_tag(tag: str, text: str): 
    if f"<{tag}>" not in text or f"</{tag}>" not in text:
        return ""
    return text[text.find(f"<{tag}>") + len(f"<{tag}>"): text.find(f"</{tag}>")].rstrip("\n").strip()


def get_unified_diff(old_content: str, new_content: str, filename: str = "file.txt") -> str:
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"{filename} (before)",
        tofile=f"{filename} (after)",
        lineterm=""
    )

    return ''.join(diff)
