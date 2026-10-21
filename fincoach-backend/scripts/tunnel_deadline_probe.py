"""Isolated dummy origin for the approved fixed-delay transport checks.

Bind only to loopback. A connector's exact-path rule must route these two
paths here; this helper never edits ingress or adds a production API route.
No query values, request bodies, LLMs or persistence are accepted.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from time import monotonic, sleep

DELAYS = {'/__fincoach_transport_probe__/120': 120,
          '/__fincoach_transport_probe__/122': 122}


class ProbeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Do not log arbitrary request paths or client information.

    def do_GET(self):
        if self.path not in DELAYS:
            self.send_error(404)
            return
        delay = DELAYS[self.path]
        started = monotonic()
        # The server is a diagnostic origin, not the agent orchestration loop.
        sleep(delay)
        payload = json.dumps({'fixed_delay_seconds': delay,
            'elapsed_seconds': round(monotonic()-started, 3)}).encode()
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            print(json.dumps({'fixed_delay_seconds': delay, 'client_disconnected': True}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Use an unprivileged local port.')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), ProbeHandler)
    print(json.dumps({'loopback_port': args.port, 'fixed_paths': list(DELAYS)}), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
