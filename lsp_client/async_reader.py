import asyncio
import json

class AsyncStreamReader:
    def __init__(self, proc):
        self.proc = proc
        self._tasks = []

    async def start_reader(self) -> None:
        """Start async readers for stdout and stderr"""
        tasks = []

        if self.proc.stdout is not None:
            tasks.append(asyncio.create_task(
                self._read_stream(self.proc.stdout, "OUT")
            ))

        if self.proc.stderr is not None:
            tasks.append(asyncio.create_task(
                self._read_stream(self.proc.stderr, "ERR")
            ))

        self._tasks = tasks

    async def _read_stream(self, stream, label: str) -> None:
        """Async stream reader using proper buffering"""
        try:
            while True:
                headers = await self._read_headers(stream)
                if headers is None:
                    break  # EOF

                content_length = self._parse_content_length(headers)

                if content_length > 0:
                    body = await stream.read(content_length)
                    if not body:
                        break  # EOF

                    try:
                        decoded = body.decode()
                        parsed = json.loads(decoded)
                        print(f"[{label}]>>", json.dumps(parsed, indent=2))
                    except (UnicodeDecodeError, json.JSONDecodeError) as e:
                        print(f"[{label}] Decode error:", e)

        except asyncio.CancelledError:
            print(f"[{label}] Reader cancelled")
            raise
        except Exception as e:
            print(f"[{label}] Error:", e)
        finally:
            print(f"[{label}] Reader finished")

    async def _read_headers(self, stream) -> bytes | None:
        """Read headers until we hit \\r\\n\\r\\n"""
        headers = b""

        while True:
            try:
                line = await stream.readline()
                if not line:
                    return None  # EOF

                headers += line
                if headers.endswith(b"\r\n\r\n"):
                    return headers

            except asyncio.IncompleteReadError:
                return None  # EOF

    def _parse_content_length(self, headers: bytes) -> int:
        """Parse content-length from headers"""
        try:
            header_str = headers.decode()
            for line in header_str.split("\r\n"):
                if line.lower().startswith("content-length:"):
                    return int(line.split(":", 1)[1].strip())
        except (UnicodeDecodeError, ValueError):
            pass
        return 0

    async def stop(self):
        """Cancel all reader tasks"""
        for task in self._tasks:
            task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()

