#!/usr/bin/env python3
"""Serves the needle page and its status, read afresh on every request.

    server.py STATUS.json [--port 8765]              the status is that file, which the job rewrites as it goes
    server.py --cmd "python3 my_status.py" [--port]  the status is what that command prints, run on every request

The status format is in README.md. The server adds "now" (this machine's clock, HH:MM) if the status has none.
"""
import argparse, datetime, http.server, json, os, shlex, socketserver, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('status', nargs='?', help='a JSON file the job writes')
    ap.add_argument('--cmd', help='a command that prints the status JSON')
    ap.add_argument('--port', type=int, default=8765)
    a = ap.parse_args()
    if not (a.status or a.cmd): ap.error('give a status file or --cmd')

    def status():
        if a.cmd:
            out = subprocess.run(shlex.split(a.cmd), capture_output=True, text=True, timeout=60, check=True).stdout
            s = json.loads(out)
        else:
            s = json.load(open(a.status))
        s.setdefault('now', datetime.datetime.now().strftime('%H:%M'))
        return s

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kw): super().__init__(*args, directory=HERE, **kw)
        def log_message(self, *args): pass
        def do_GET(self):
            if not self.path.startswith('/status'): return super().do_GET()
            try: b, code = json.dumps(status()).encode(), 200
            except Exception as e: b, code = json.dumps({'error': str(e)}).encode(), 500
            self.send_response(code); self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(b)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(('127.0.0.1', a.port), H) as srv:
        print(f'http://localhost:{a.port}/', flush=True)
        srv.serve_forever()


if __name__ == '__main__':
    main()
