#!/usr/bin/env python3
"""Start Photo Cloud.

  python run.py --folder ~/Pictures                       # local folder
  python run.py --source gdrive --folder <folder link>    # Google Drive
  python run.py --source dropbox --folder /Photos         # Dropbox
  python run.py --source gphotos                          # your saved Google Photos picks
"""
import argparse
import threading
import webbrowser

from photocloud.cache import DiskCache
from photocloud.errors import AuthRequired, SourceError
from photocloud.server import AppState, make_context, serve
from photocloud.sources import KINDS


def main() -> None:
    ap = argparse.ArgumentParser(description="Photo Cloud")
    ap.add_argument("--source", choices=KINDS, default="local", help="where photos come from")
    ap.add_argument("--folder", help="local path, Drive folder link/ID, or Dropbox path (optional)")
    ap.add_argument("--recursive", action="store_true", help="include subfolders")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--clear-cache", action="store_true", help="delete cached Drive/Dropbox images and exit")
    args = ap.parse_args()

    ctx = make_context(args.port)
    if args.clear_cache:
        print(f"Removed {DiskCache(ctx.home / 'cache').clear()} cached files")
        return

    state = AppState(ctx)
    if args.folder or args.source != "local":
        try:
            count = state.load(args.source, {"path": args.folder or "", "recursive": args.recursive})
            print(f"Loaded {count} photos")
        except AuthRequired:
            print("Not connected yet: use the settings panel in the browser to connect.")
        except SourceError as exc:
            print(f"Warning: {exc}")

    host = "127.0.0.1"  # local only
    httpd = serve(host, args.port, state)
    url = f"http://{host}:{args.port}/"
    print(f"Photo Cloud running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
