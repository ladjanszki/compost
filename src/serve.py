#!/usr/bin/env python3
"""
serve.py — hand the HTML view to a browser, and nothing else.

This does not render. `render` is the only thing that writes views, and it
already refuses on a graph that fails `check`, so every file under
`default-html/` was produced from a graph that was sound at the time. The
guarantee lives where the files are made; serving them needs no opinion of its
own. Run `compost render` in another terminal and refresh the page.

That is also why this module knows nothing about records, graphs or views. It
locates the base — the one thing it cannot do without — and from there it is a
directory and a port.
"""
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import store as S

PORT = 7373
HOST = "127.0.0.1"


class Handler(SimpleHTTPRequestHandler):
    """Static files, never cached.

    `SimpleHTTPRequestHandler` answers `If-Modified-Since` with a 304, and
    `Last-Modified` is only accurate to the second. A `render` landing in the
    same second as your last page load therefore serves the old page on
    refresh — measured, not theorised. These are small local files regenerated
    by a command you just ran, so there is nothing to gain from caching them
    and a stale refresh costs more than every re-read ever will.
    """

    def send_head(self):
        # Drop the client's revalidation headers before the base class can act
        # on them. "Not modified" derived from a one-second timestamp is a
        # guess, and a wrong guess serves yesterday's page; no-store below asks
        # the browser not to ask, and this makes the answer right even when
        # something asks anyway.
        for h in ("If-Modified-Since", "If-None-Match"):
            if h in self.headers:
                del self.headers[h]
        return super().send_head()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def make_server(directory: Path, port: int = PORT) -> ThreadingHTTPServer:
    """Bind and return, without serving. Split out so a test can drive it.

    Binds the loopback address only. A knowledge base is not something to put
    on the local network by accident, and `0.0.0.0` is exactly that accident.
    Threading because a browser opens several connections at once and a
    single-threaded server makes them queue.
    """
    ThreadingHTTPServer.allow_reuse_address = True
    return ThreadingHTTPServer((HOST, port), partial(Handler, directory=str(directory)))


def main(argv) -> int:
    port = PORT
    args = list(argv[1:])
    while args:
        a = args.pop(0)
        if a in ("-p", "--port"):
            if not args or not args[0].lstrip("-").isdigit():
                print(f"usage: compost serve [-p PORT]   (default {PORT})")
                return 2
            port = int(args.pop(0))
        else:
            print(f"usage: compost serve [-p PORT]   (default {PORT})")
            return 2

    try:
        st = S.Store.find()
    except S.NotABase as e:
        print(e)
        return 1

    root = st.views / "default-html"
    if not root.is_dir():
        print(f"no views yet at {root.relative_to(st.root)}/ — run compost render")
        return 1

    try:
        srv = make_server(root, port)
    except OSError as e:
        print(f"cannot serve on {HOST}:{port}: {e}")
        return 1

    pages = len(list(root.glob("*.html")))
    print(f"  {pages} pages from {root.relative_to(st.root)}/")
    print(f"  http://{HOST}:{port}  — ctrl-c to stop, compost render to update")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
