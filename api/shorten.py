import os
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
            if not os.environ.get("GEMINI_API_KEY"):
                error_response(
                    self,
                    500,
                    "GEMINI_API_KEY is not configured on the server",
                )
                return

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

            sibling_verbs = data.get("sibling_verbs")
            if sibling_verbs is not None and not isinstance(sibling_verbs, list):
                error_response(self, 400, "sibling_verbs must be an array of strings")
                return

            result = process_latex(
                data["input_latex"],
                data["reference_latex"],
                sibling_verbs=sibling_verbs,
            )

            payload = result.to_dict()
            payload["limits"] = {"heading": limits.heading, "body": limits.body}
            payload["fits"] = (
                result.new.heading <= limits.heading
                and result.new.body <= limits.body
            )
            send_json(self, 200, payload)
        except Exception as exc:
            handle_exception(self, exc)
