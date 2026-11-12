#!/usr/bin/env python3
"""Serves chyron.html with a made-up rehearsal in /state, to see a chyron style move without the player.

    python3 player/chyron_demo.py [--port 8767]
    then open http://localhost:8767/?style=broadcast  (or any of chyron.html's options)

It plays through a few bars, pauses, changes part, loops, moves on a section, goes off the air and comes back with
another song, and shows the note names card, about 60 seconds round.
"""
import argparse, http.server, json, os, socketserver, time

HERE = os.path.dirname(os.path.abspath(__file__))


def script():
    """(seconds, state) in order"""
    out = []
    marks = ['Intro', '12', '20', '33']

    def st(song, loc, part='Tutti', playing=True, loop=None, cur='12', marked=marks):
        return {'song': song, 'location': loc, 'part': part, 'playing': playing,
                'loop': loop and f'Loop from {loop[0]} to {loop[1]}', 'loop_bars': loop,
                'sections': [{'name': n, 'current': n == cur} for n in marked]}

    out.append((2.5, {'song': None}))
    out.append((2.5, st('Light', '12', playing=False)))
    for loc in ['12', '1 after 12', '2 after 12', 'Bar 15', 'Bar 16', 'Bar 17']:
        out.append((1.3, st('Light', loc)))
    out.append((3, st('Light', 'Bar 17', playing=False)))
    out.append((2.5, st('Light', 'Bar 15', part='Alto 1', playing=False)))
    for loc in ['Bar 15', 'Bar 16', 'Bar 17', '2 before 20']:
        out.append((1.3, st('Light', loc, part='Alto 1', loop=['15', '18'])))
    out.append((2.5, st('Light', '2 before 20', part='Alto 1 + Tenor 2', playing=False, loop=['15', '18'])))
    out.append((2.5, st('Light', '20', part='Alto 1 + Tenor 2', playing=False, cur='20')))
    for loc in ['20', '1 after 20', '2 after 20', 'Bar 23 (2nd time)']:
        out.append((1.3, st('Light', loc, cur='20')))
    out.append((3, st('Light', 'Bar 23 (2nd time)', playing=False, cur='20')))
    out.append((2.5, {'song': None}))
    secs = ['A', 'B', 'C', 'D', 'E']
    for loc, cur in [('A', 'A'), ('1 after A', 'A'), ('A: 9', 'A'), ('2 before B', 'A'), ('1 before B', 'A'), ('B', 'B'), ('1 after B', 'B')]:
        out.append((1.3, st('When You Believe', loc, cur=cur, marked=secs)))
    out.append((3, st('When You Believe', '1 after B', part='Soprano 1', playing=False, cur='B', marked=secs)))
    # the note names card, over a pause
    out.append((6, dict(st('When You Believe', '1 after B', part='Soprano 1', playing=False, cur='B', marked=secs), notes_card=True)))
    out.append((2, st('When You Believe', '1 after B', part='Soprano 1', playing=False, cur='B', marked=secs)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8767)
    a = ap.parse_args()
    steps = script()
    total = sum(d for d, _ in steps)
    start = time.time()

    def state():
        t = (time.time() - start) % total
        for d, s in steps:
            if t < d: return s
            t -= d
        return steps[-1][1]

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            path = self.path.split('?')[0]
            if path == '/state': body, kind = json.dumps(state()).encode(), 'application/json'
            elif path in ('/', '/index.html'): body, kind = open(os.path.join(HERE, 'chyron.html'), 'rb').read(), 'text/html; charset=utf-8'
            else: self.send_error(404); return
            self.send_response(200); self.send_header('Content-Type', kind); self.send_header('Cache-Control', 'no-store')
            self.end_headers(); self.wfile.write(body)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(('127.0.0.1', a.port), H) as srv:
        print(f'http://localhost:{a.port}/?style=broadcast', flush=True)
        srv.serve_forever()


if __name__ == '__main__':
    main()
