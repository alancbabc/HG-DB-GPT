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
                {
                    "models": [
                        {"name": "local-llm"},
                        {"name": "fallback-llm"},
                        {"name": "local-embed"},
                    ]
                }
            )
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        if self.path == "/api/generate" and payload["model"] in (
            "local-llm",
            "fallback-llm",
        ):
            assert payload["keep_alive"] == 0
            self._send(
                {
                    "response": "健康",
                    "total_duration": 2_000_000_000,
                    "load_duration": 1_000_000_000,
                    "eval_count": 10,
                    "eval_duration": 500_000_000,
                }
            )
        elif self.path == "/api/embed" and payload["model"] == "local-embed":
            assert payload["keep_alive"] == 0
            self._send(
                {
                    "embeddings": [[0.1, 0.2, 0.3]],
                    "total_duration": 1_000_000_000,
                    "load_duration": 800_000_000,
                }
            )
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
    assert report["details"]["mainGeneration"]["tokensPerSecond"] == 20.0
    assert report["details"]["embedding"]["loadSeconds"] == 0.8


def test_check_ollama_reports_missing_model(ollama_stub):
    report = check_ollama(ollama_stub, "missing-llm", "local-embed", 2)

    assert report["success"] is False
    assert report["checks"]["llmInstalled"] is False


def test_check_ollama_validates_fallback_generation(ollama_stub):
    report = check_ollama(
        ollama_stub,
        "local-llm",
        "local-embed",
        2,
        fallback_llm_model="fallback-llm",
    )

    assert report["success"] is True
    assert report["checks"]["fallbackLlmInstalled"] is True
    assert report["checks"]["fallbackGenerationWorks"] is True


def test_check_ollama_rejects_non_loopback_url():
    with pytest.raises(ValueError, match="loopback"):
        check_ollama("http://192.0.2.1:11434", "llm", "embed", 1)


def test_check_ollama_can_enforce_runtime_version(ollama_stub):
    matching = check_ollama(
        ollama_stub,
        "local-llm",
        "local-embed",
        2,
        expected_version="test",
    )
    assert matching["success"] is True
    assert matching["checks"]["versionMatches"] is True

    mismatching = check_ollama(
        ollama_stub,
        "local-llm",
        "local-embed",
        2,
        expected_version="other",
    )
    assert mismatching["success"] is False
    assert mismatching["checks"]["versionMatches"] is False
