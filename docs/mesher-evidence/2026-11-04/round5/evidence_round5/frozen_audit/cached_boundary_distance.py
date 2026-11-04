"""Cached native OCCT distances to a compound of trimmed boundary faces."""
from pathlib import Path
import os
import selectors
import subprocess
import time
import numpy as np

HERE = Path(__file__).resolve().parent
PREFIX = HERE.parents[2] / "caelab_mesher_engine_20261104/smesh_layer/native_env"

class CADBoundaryDistance:
    def __init__(self, cad, tolerance=1e-9, log=None, query_timeout=120):
        # Executable mode is not retained by every workspace artifact sync.
        # This is the newly built Round4 executable, never an earlier asset.
        (HERE / "cad_boundary_query").chmod(0o755)
        self.log = open(log, "w") if log else open(os.devnull, "w")
        self.process = subprocess.Popen([str(HERE / "cad_boundary_query"), str(cad), str(tolerance)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
            bufsize=0,
            env=dict(os.environ, LD_LIBRARY_PATH=str(PREFIX / "lib")))
        self.timeout = query_timeout
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.buffer = b""

    def query(self, points):
        points = np.asarray(points, dtype=float).reshape(-1, 3)
        if not np.isfinite(points).all():
            raise ValueError("Nonfinite CAD query")
        result = []
        for start in range(0, len(points), 128):
            batch = points[start:start+128]
            self.process.stdin.write("".join("%.17g %.17g %.17g\n" % tuple(p) for p in batch).encode("ascii"))
            self.process.stdin.flush()
            deadline = time.monotonic() + self.timeout
            for _ in batch:
                while b"\n" not in self.buffer:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not self.selector.select(remaining):
                        raise TimeoutError("Native CAD query batch exceeded budget")
                    chunk = os.read(self.process.stdout.fileno(), 65536)
                    if not chunk:
                        raise RuntimeError("Native CAD boundary query closed unexpectedly")
                    self.buffer += chunk
                line, self.buffer = self.buffer.split(b"\n", 1)
                values = np.fromstring(line.decode("ascii"), sep=" ")
                if values.shape != (5,) or not np.isfinite(values).all() or values[0] < 0:
                    raise ValueError("Invalid native boundary distance/witness")
                result.append(values)
        return np.asarray(result, dtype=float).reshape(-1, 5)

    def distance(self, points):
        return self.query(points)[:, 0]

    def close(self):
        if self.process.stdin and not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.selector.close()
        self.log.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
