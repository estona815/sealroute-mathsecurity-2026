"""Anonymous public ZeroGPU API. No account, cookies, paid fallback or POST retry."""
import json
import time
import urllib.request
from sealroute import canonical

ORIGIN = "https://zacheus10-free-ai-chat.hf.space"
BASE = ORIGIN + "/gradio_api/call/v2/generate"
MODEL = "Qwen/Qwen3-4B-Instruct-2507"
BACKEND = "anonymous ZeroGPU daily quota"
MAX_NEW_TOKENS = 64
SUBMISSION_MAX_BYTES = 4096
SSE_MAX_BYTES = 100000


def bounded_json(response):
    raw = response.read(SUBMISSION_MAX_BYTES + 1)
    if len(raw) > SUBMISSION_MAX_BYTES:
        raise RuntimeError("Oversized submission response; no automatic retry")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("Unexpected submission response; no automatic retry")
    return value


def payload_for(prompt):
    if not isinstance(prompt, str) or not 1 <= len(prompt) <= 16000:
        raise ValueError("Bounded nonempty prompt required")
    return {"message": prompt, "max_new_tokens": MAX_NEW_TOKENS, "temperature": 0.1}


def request_model(prompt, *, on_submitted=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(BASE, data=canonical(payload_for(prompt)),
                                 headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=25) as response:
        submitted = bounded_json(response)
    event_id = submitted.get("event_id", "")
    if (not isinstance(event_id, str) or len(event_id) != 32
            or any(c not in "0123456789abcdef" for c in event_id)):
        raise RuntimeError("Unexpected event identifier; no retry")
    if on_submitted:
        on_submitted(event_id)
    lines, event, received = [], "", 0
    deadline = time.monotonic() + 90
    with opener.open(ORIGIN + "/gradio_api/call/generate/" + event_id, timeout=55) as response:
        while True:
            raw = response.readline(SSE_MAX_BYTES - received + 1)
            if not raw:
                break
            received += len(raw)
            if received > SSE_MAX_BYTES:
                raise RuntimeError("Oversized SSE response; no retry")
            if time.monotonic() > deadline:
                raise TimeoutError("SSE polling budget reached; no automatic retry")
            line = raw.decode("utf-8").rstrip("\r\n")
            lines.append(line)
            if line.startswith("event: "):
                event = line[7:]
            if line.startswith("data: ") and event in ("complete", "error"):
                if event == "error":
                    return {"event_id": event_id, "terminal": "error", "sse": lines}
                result = json.loads(line[6:])
                if not isinstance(result, list) or not result or not isinstance(result[0], str):
                    raise RuntimeError("Unexpected model result; no resubmit")
                return {"event_id": event_id, "terminal": "complete", "response": result[0],
                        "sse": lines, "model": MODEL, "backend": BACKEND}
    raise RuntimeError("No terminal SSE event; no automatic retry")
