"""Parent-side deadlines, output bounds and process-group cancellation."""
from dataclasses import dataclass
import os
import selectors
import signal
import subprocess
import time


class ProcessError(RuntimeError):
    pass


@dataclass
class Result:
    returncode: int
    stdout: str


def run(argv, *, timeout, cwd=None, env=None, stdin='', max_output=1_000_000, tick=None):
    if timeout <= 0:
        raise ProcessError('Execution deadline exceeded')
    # A temporary file avoids blocking the supervisor on a worker that never reads stdin.
    import tempfile
    with tempfile.TemporaryFile() as input_file:
        input_file.write(stdin.encode())
        input_file.seek(0)
        p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=input_file, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, start_new_session=True)
        chunks = bytearray()
        started = last_tick = time.monotonic()
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(p.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    now = time.monotonic()
                    if now - started >= timeout:
                        raise ProcessError('Execution deadline exceeded')
                    if tick and now - last_tick >= 15:
                        tick(now - started)
                        last_tick = now
                    for key, _ in selector.select(min(0.1, timeout)):
                        data = os.read(key.fileobj.fileno(), 65536)
                        if not data:
                            selector.unregister(key.fileobj)
                        else:
                            chunks.extend(data)
                            if len(chunks) > max_output:
                                raise ProcessError('Worker output limit exceeded')
                p.wait(timeout=max(0.01, timeout - (time.monotonic() - started)))
            return Result(p.returncode, chunks.decode(errors='replace'))
        except subprocess.TimeoutExpired as exc:
            raise ProcessError('Execution deadline exceeded') from exc
        finally:
            # Always kill residual descendants, including when the parent exited normally.
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait()
            p.stdout.close()
