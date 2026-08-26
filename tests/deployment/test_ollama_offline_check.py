import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scripts.windows.check_ollama_offline import check_ollama


class _OllamaStub(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/version":
            self._send({"version": "test"})
        elif self.path == "/api/tags":
            self._send(
                {"models": [{"name": "local-llm"}, {"name": "local-embed"}]}
            )
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        if self.path == "/api/generate" and payload["model"] == "local-llm":
            self._send({"response": "健康"})
        elif self.path == "/api/embed" and payload["model"] == "local-embed":
            self._send({"embeddings": [[0.1, 0.2, 0.3]]})
        else:
            self.send_error(400)


@pytest.fixture
def ollama_stub():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OllamaStub)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_check_ollama_validates_generation_and_embedding(ollama_stub):
    report = check_ollama(ollama_stub, "local-llm", "local-embed", 2)

    assert report["success"] is True
    assert all(report["checks"].values())
    assert report["details"]["embeddingDimensions"] == 3


def test_check_ollama_reports_missing_model(ollama_stub):
    report = check_ollama(ollama_stub, "missing-llm", "local-embed", 2)

    assert report["success"] is False
    assert report["checks"]["llmInstalled"] is False


def test_check_ollama_rejects_non_loopback_url():
    with pytest.raises(ValueError, match="loopback"):
        check_ollama("http://192.0.2.1:11434", "llm", "embed", 1)
