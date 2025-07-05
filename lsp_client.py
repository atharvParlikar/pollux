import subprocess
import threading
import json
import time
from typing import Any, IO
from lsp_types import Position

class LSPClient:
    def __init__(self, server_command: list[str], project_uri: str) -> None:
        self.proc: subprocess.Popen[bytes] = subprocess.Popen(
            server_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0
        )
        self._start_reader()
        self.project_uri: str = project_uri
        self.request_id: int = 1

    def get_next_id(self) -> int:
        self.request_id += 1
        return self.request_id

    def _start_reader(self) -> None:
        def read_stream(stream: IO[bytes], label: str) -> None:
            while True:
                headers = b""
                while True:
                    line = stream.readline()
                    if not line:
                        return  # EOF
                    headers += line
                    if headers.endswith(b"\r\n\r\n"):
                        break

                try:
                    header_str = headers.decode()
                    content_length = 0
                    for header_line in header_str.split("\r\n"):
                        if header_line.lower().startswith("content-length:"):
                            content_length = int(header_line.split(":")[1].strip())
                            break

                    if content_length > 0:
                        body = stream.read(content_length)
                        decoded = body.decode()
                        print(f"[{label}]>>", json.dumps(json.loads(decoded), indent=2))
                except Exception as e:
                    print(f"[{label}] Error:", e)

        if self.proc.stdout is not None:
            threading.Thread(
                target=read_stream, args=(self.proc.stdout, "OUT"), daemon=True
            ).start()

        if self.proc.stderr is not None:
            threading.Thread(
                target=read_stream, args=(self.proc.stderr, "ERR"), daemon=True
            ).start()

    def send(self, payload: dict[str, Any]) -> None:
        content = json.dumps(payload)
        message = f"Content-Length: {len(content)}\r\n\r\n{content}"
        if self.proc.stdin is not None:
            self.proc.stdin.write(message.encode())
            self.proc.stdin.flush()

    def initialize(self) -> None:
        init_payload = {
            "jsonrpc": "2.0",
            "id": self.get_next_id(),
            "method": "initialize",
            "params": {
                "processId": None,
                "rootUri": self.project_uri,
                "capabilities": {
                    "textDocument": {
                        "hover": {},
                        "completion": {
                            "completionItem": {
                                "snippetSupport": True
                            }
                        },
                        "definition": {},
                        "references": {},
                        "signatureHelp": {
                            "signatureInformation": {
                                "documentationFormat": ["markdown", "plaintext"]
                            }
                        },
                        "synchronization": {
                            "didOpen": True,
                            "didChange": True,
                            "didClose": True
                        },
                        "semanticTokens": {
                            "requests": {
                                "range": True,
                                "full": {
                                    "delta": False
                                }
                            },
                            "tokenTypes": [],
                            "tokenModifiers": [],
                            "formats": ["relative"]
                        }
                    },
                    "workspace": {
                        "workspaceFolders": True,
                        "didChangeWatchedFiles": {
                            "dynamicRegistration": True
                        }
                    }
                },
                "trace": "off"
            }
        }

        self.send(init_payload)

    def did_open(self, file_uri: str, content: str, language_id: str = "typescript") -> None:
        """Notify the server that a document has been opened"""
        self.send({
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {
                "textDocument": {
                    "uri": file_uri,
                    "languageId": language_id,
                    "version": 1,
                    "text": content
                }
            }
        })

    def goto_definition(self, document_uri: str, position: Position):
        self.send({
            "jsonrpc": "2.0",
            "id": self.get_next_id(),
            "method": "textDocument/definition",
            "params": {
                "textDocument": {
                    "uri": document_uri
                },
                "position": {
                    "line": position["line"],
                    "character": position["character"]
                }
            }
        })

    def hover(self, file_uri: str, position: Position):
        self.send({
            "jsonrpc": "2.0",
            "id": self.get_next_id(),
            "method": "textDocument/hover",
            "params": {
                "textDocument": {
                    "uri": file_uri
                },
                "position": {
                    "line": position["line"],
                    "character": position["character"]
                },
            },
        })

def main() -> None:
    client = LSPClient(["pyright-langserver", "--stdio"], "file:///Users/atharvparlikar/test/")

    client.initialize()
    time.sleep(0.5)

    client.send({
        "jsonrpc": "2.0",
        "method": "initialized",
        "params": {}
    })
    time.sleep(0.5)

    client.send({
        "jsonrpc": "2.0",
        "method": "workspace/didChangeWorkspaceFolders",
        "params": {
            "event": {
                "added": [{
                    "uri": client.project_uri,
                    "name": client.project_uri.split("/")[-1]
                }],
                "removed": []
            }
        }
    })
    time.sleep(0.5)

    file_text = ''
    with open('/Users/atharvparlikar/test/foo.py') as f:
        file_text = f.read()
    print(file_text)

    client.did_open("file:///Users/atharvparlikar/test/foo.py", file_text, "python")
    time.sleep(1)

    client.send({
        "jsonrpc": "2.0",
        "id": client.get_next_id(),
        "method": "textDocument/hover",
        "params": {
            "textDocument": {
                "uri": "file:///Users/atharvparlikar/test/foo.py"
            },
            "position": {
                "line": 2,
                "character": 4
            }
        }
    })
    time.sleep(2)

if __name__ == "__main__":
    main()
