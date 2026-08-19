#!/usr/bin/env python3
"""
test_serve.py — the static server's promises.

`serve` renders nothing, so none of these touch a graph. That is the design:
`render` is the only thing that writes views and it already refuses on a graph
that fails `check`, so the guarantee lives where the files are made. What is
left to pin here is delivery — that a re-render is visible on the next request,
that the socket is on loopback and nowhere else, and that no request can reach
a file outside the served directory.

Every server here binds port 0 and lets the OS choose, so the suite never
fights a fixed port with whatever else is running.
"""
import socket
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import serve as SRV  # noqa: E402

# The real command logs every request, which is wanted when a person is running
# it and noise when nine cases are.
SRV.Handler.log_message = lambda *a, **k: None


class Served:
    """A bound server on an OS-chosen port, running for the duration."""

    def __init__(self, directory):
        self.srv = SRV.make_server(Path(directory), 0)
        self.port = self.srv.server_address[1]
        self.host = self.srv.server_address[0]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.srv.shutdown()
        self.srv.server_close()

    def get(self, path, headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                     headers=headers or {})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), b""


def main():
    results = []

    def case(name, fn):
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append((ok, name, detail))

    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "default-html"
        root.mkdir()
        (root / "index.html").write_text("<h1>index</h1>")
        (root / "a.html").write_text("FIRST")
        secret = Path(d) / "secret.txt"
        secret.write_text("not for the browser")

        with Served(root) as s:

            def index():
                code, _, body = s.get("/")
                return code == 200 and b"index" in body, "index.html at /"
            case("the root path serves index.html", index)

            def document():
                code, _, body = s.get("/a.html")
                return code == 200 and body == b"FIRST", "exact bytes"
            case("a document page is served", document)

            def missing():
                code, _, _ = s.get("/nope.html")
                return code == 404, "404"
            case("an unknown path is 404, not a traceback", missing)

            def traversal():
                tries = ["/../secret.txt", "/../../secret.txt",
                         "/%2e%2e/secret.txt", "/a/../../secret.txt"]
                codes = {s.get(t)[0] for t in tries}
                leaked = any(b"not for the browser" in s.get(t)[2] for t in tries)
                return not leaked and 200 not in codes, f"{len(tries)} refused"
            case("nothing outside the served directory is reachable", traversal)

            def rerender_is_visible():
                # The whole point of serving without rendering: `render` writes
                # the file, the next request sees it. Written with the same
                # mtime second on purpose — that is the case where a 304 would
                # have served the old page.
                before = s.get("/a.html")[2]
                st = (root / "a.html").stat()
                (root / "a.html").write_text("SECOND")
                import os
                os.utime(root / "a.html", (st.st_atime, st.st_mtime))
                lm = s.get("/a.html")[1].get("Last-Modified")
                code, _, after = s.get("/a.html", {"If-Modified-Since": lm})
                return (before == b"FIRST" and code == 200 and after == b"SECOND",
                        "new bytes, same mtime second")
            case("a rewritten file is served fresh, even conditionally",
                 rerender_is_visible)

            def never_cached():
                _, hdrs, _ = s.get("/a.html")
                return hdrs.get("Cache-Control") == "no-store", \
                    hdrs.get("Cache-Control")
            case("responses say no-store", never_cached)

            def loopback_only():
                # Binding 0.0.0.0 would put a personal knowledge base on the
                # local network by accident.
                return s.host == "127.0.0.1", s.host
            case("the socket is bound to loopback, not every interface",
                 loopback_only)

        def chosen_port():
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                free = probe.getsockname()[1]
            srv = SRV.make_server(root, free)
            try:
                return srv.server_address[1] == free, f"port {free}"
            finally:
                srv.server_close()
        case("an explicit port is the port bound", chosen_port)

        def default_is_not_a_common_one():
            common = {80, 443, 3000, 5000, 7000, 8000, 8080, 8888, 9000}
            return (SRV.PORT not in common and 1024 < SRV.PORT < 49152,
                    f"{SRV.PORT}, outside the ephemeral range")
        case("the default port avoids the crowded ones", default_is_not_a_common_one)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<56} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} serve guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
