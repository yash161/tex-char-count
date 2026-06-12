from http.server import BaseHTTPRequestHandler

from _helpers import (
    error_response,
    handle_exception,
    handle_options,
    read_json_body,
    require_fields,
    send_json,
)
from tex_char_count import parse_cc_limits, process_latex


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        handle_options(self)

    def do_POST(self):
        try:
            data, err = read_json_body(self)
            if err:
                error_response(self, 400, err)
                return

            err = require_fields(data, ("input_latex", "reference_latex"))
            if err:
                error_response(self, 400, err)
                return

            limits = parse_cc_limits(data["reference_latex"])
            if not limits:
                error_response(
                    self,
                    400,
                    "reference_latex must include a CC comment "
                    "(% heading CC: orig=..., new=... | body CC: ...)",
                )
                return

            result = process_latex(
                data["input_latex"],
                data["reference_latex"],
                count_only=True,
            )

            send_json(
                self,
                200,
                {
                    "limits": {"heading": limits.heading, "body": limits.body},
                    "input": {
                        "heading": result.orig.heading,
                        "body": result.orig.body,
                    },
                    "fits": (
                        result.orig.heading <= limits.heading
                        and result.orig.body <= limits.body
                    ),
                    "notes": result.notes,
                    "text": result.text,
                },
            )
        except Exception as exc:
            handle_exception(self, exc)
