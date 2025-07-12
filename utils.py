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



def llm_completion(prompt: str, client, model, console, retries: int, retry_delay: float = 1.0) -> str:
    """
    Make an LLM completion call using the specified client and model, with retry logic and error handling.
    Arguments:
        prompt (str): The prompt string to send to the LLM.
        client: The LLM client instance (e.g., OpenAI).
        model: Model name/id for the LLM.
        console: Console object for printing errors to user.
        retries (int): Maximum number of retry attempts.
        retry_delay (float): Base delay between retries.
    Returns:
        str: Text result from the LLM.
    Raises:
        SystemExit: If all retries are exhausted without getting a response.
    """
    if not prompt or not prompt.strip():
        console.print("Prompt cannot be empty")
        return "Prompt cannot be empty"

    prompt_ = {
        "role": "user",
        "content": prompt
    }
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[prompt_],
                timeout=30,
            )
            response_str = response.choices[0].message.content
            if not response_str:
                console.print("Empty response from LLM")
                return "Empty response from LLM"
            return response_str
        except Exception as e:
            if attempt < retries - 1:
                import time
                time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
            else:
                console.print(f"Failed to get LLM completion after {retries} attempts: {e}")
    print("Can't get LLM response, quitting...")
    exit(1)
