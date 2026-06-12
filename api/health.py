from http.server import BaseHTTPRequestHandler

from _helpers import handle_options, send_json


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        handle_options(self)

    def do_GET(self):
        send_json(
            self,
            200,
            {
                "status": "ok",
                "service": "tex-char-count",
                "endpoints": {
                    "GET /api/health": "health check",
                    "POST /api/count": "count heading/body chars vs reference limits",
                    "POST /api/shorten": "shorten LaTeX bullet to fit reference limits",
                },
            },
        )
