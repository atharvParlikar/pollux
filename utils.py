def extract_tag(tag: str, text: str):
    return text[text.find(f"<{tag}>") + len(f"<{tag}>"): text.find(f"</{tag}>")]

