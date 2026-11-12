#!/usr/bin/env python3
"""Serves the needle page and its status, read afresh on every request.

    server.py STATUS.json [--port 8765]              the status is that file, which the job rewrites as it goes
    server.py --cmd "python3 my_status.py" [--port]  the status is what that command prints, run on every request
    --host 0.0.0.0                                    also answer other devices on this network (a phone), not only this Mac

It serves only the pages (*.html here) and /status, so the logs and files beside them stay private.

The status format is in README.md. The server adds "now" (this machine's clock, HH:MM) if the status has none.
"""
import argparse, datetime, http.server, json, os, shlex, socketserver, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('status', nargs='?', help='a JSON file the job writes')
    ap.add_argument('--cmd', help='a command that prints the status JSON')
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--host', default='127.0.0.1', help='0.0.0.0 to answer other devices on this network too')
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
            if not self.path.startswith('/status'):
                page = self.path.split('?')[0].lstrip('/') or 'index.html'
                if '/' in page or page.startswith('.') or not page.endswith('.html') or not os.path.isfile(os.path.join(HERE, page)):
                    self.send_error(404); return
                return super().do_GET()
            try: b, code = json.dumps(status()).encode(), 200
            except Exception as e: b, code = json.dumps({'error': str(e)}).encode(), 500
            self.send_response(code); self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(b)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer((a.host, a.port), H) as srv:
        print(f'http://localhost:{a.port}/', flush=True)
        if a.host != '127.0.0.1':
            # the address of the interface the default route uses (Wi-Fi or Ethernet, whichever enN it is)
            route = subprocess.run(['route', '-n', 'get', 'default'], capture_output=True, text=True).stdout
            dev = next((l.split()[-1] for l in route.splitlines() if 'interface:' in l), 'en0')
            ip = subprocess.run(['ipconfig', 'getifaddr', dev], capture_output=True, text=True).stdout.strip()
            if ip: print(f'from another device on this network: http://{ip}:{a.port}/', flush=True)
        srv.serve_forever()


if __name__ == '__main__':
    main()
