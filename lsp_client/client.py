# pyright: reportUnusedCallResult=false

import asyncio
import subprocess
import json
import threading
from typing import IO, Any
from .lsp_types import Position

class LSPClient:
    def __init__(self, server_command: list[str], project_uri: str, loop: asyncio.AbstractEventLoop) -> None:
        self.loop: asyncio.AbstractEventLoop = loop
        self.proc: subprocess.Popen[bytes] = subprocess.Popen(
            server_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0
        )
        self._notification_event: asyncio.Event | None = None
        self.project_uri: str = project_uri
        self.request_id: int = 0
        self._inflight: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._start_reader()


    async def _resolve_future(self, response_id: int, result: dict[str, Any]):
        fut = self._inflight.pop(response_id, None)
        if fut is not None and not fut.done():
            fut.set_result(result)

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
                        lsp_response: dict[str, Any] = json.loads(decoded)

                        response_id = lsp_response.get("id")

                        if response_id is not None and response_id in self._inflight:
                            asyncio.run_coroutine_threadsafe(
                                self._resolve_future(response_id, lsp_response),
                                self.loop
                            )

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

    def get_next_id(self) -> int:
        self.request_id += 1
        return self.request_id

    async def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        req_id = self.get_next_id()
        fut: asyncio.Future[dict[str, Any]] = asyncio.Future()
        self._inflight[req_id] = fut

        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            **payload
        }

        content = json.dumps(request)
        message = f"Content-Length: {len(content)}\r\n\r\n{content}"
        if self.proc.stdin is not None:
            self.proc.stdin.write(message.encode())
            self.proc.stdin.flush()

        return await fut


    async def send_notification(self, payload: dict[str, Any]) -> None:
        self._notification_event = asyncio.Event()

        request = {
            "jsonrpc": "2.0",
            **payload
        }

        content = json.dumps(request)
        message = f"Content-Length: {len(content)}\r\n\r\n{content}"
        if self.proc.stdin is not None:
            self.proc.stdin.write(message.encode())
            self.proc.stdin.flush()

        # Wait for next incoming message (that should be in response to this notification)
        try:
            await asyncio.wait_for(self._notification_event.wait(), timeout=0.5)
        except asyncio.TimeoutError:
            print(f"[WARN] Timeout while waiting for response to notification {payload['method']}")


    async def initialize(self) -> dict[str, Any]:
        init_payload = {
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

        init_res = await self.send(init_payload)

        await self.send_notification({
            "method": "initialized",
            "params": {}
        })

        await self.send_notification({
            "method": "workspace/didChangeWorkspaceFolders",
            "params": {
                "event": {
                    "added": [{
                        "uri": self.project_uri,
                        "name": self.project_uri.split("/")[-1]
                    }],
                    "removed": []
                }
            }
        })

        return init_res


    async def did_open(self, file_uri: str, content: str, language_id: str = "typescript") -> None:
        """Notify the server that a document has been opened"""
        await self.send_notification({
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

    async def goto_definition(self, document_uri: str, position: Position) -> dict[str, Any]:
        return await self.send({
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

    async def hover(self, file_uri: str, position: Position) -> dict[str, Any]:
        return await self.send({
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

async def main() -> None:
    loop = asyncio.get_event_loop()
    client = LSPClient(["pyright-langserver", "--stdio"], "file:///Users/atharvparlikar/test/", loop)

    _ = await client.initialize()

    hover_res = await client.hover(file_uri='file:///Users/atharvparlikar/test/foo.py', position={ "line": 2, "character": 4 })

    print("[Hover res]\n", json.dumps(hover_res["result"], indent=2))

if __name__ == "__main__":
    asyncio.run(main())

