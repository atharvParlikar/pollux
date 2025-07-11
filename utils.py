def extract_tag(tag: str, text: str): 
    if f"<{tag}>" not in text or f"</{tag}>" not in text:
        return ""
    return text[text.find(f"<{tag}>") + len(f"<{tag}>"): text.find(f"</{tag}>")].rstrip("\n").strip()

