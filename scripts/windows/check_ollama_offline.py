"""Validate local Ollama LLM and embedding models without internet access."""

import argparse
import ipaddress
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict


def _request_json(
    base_url: str,
    path: str,
    timeout: float,
    payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    data = None
    headers = {}
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}", data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _require_loopback(base_url: str) -> None:
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme != "http" or not parsed.hostname:
        raise ValueError("Ollama URL must be an http URL with a host")
    try:
        is_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        is_loopback = parsed.hostname.lower() == "localhost"
    if not is_loopback:
        raise ValueError("Ollama URL must use a loopback address in production")


def check_ollama(
    base_url: str,
    llm_model: str,
    embedding_model: str,
    timeout: float,
    fallback_llm_model: str | None = None,
) -> Dict[str, Any]:
    _require_loopback(base_url)
    checks: Dict[str, bool] = {}
    details: Dict[str, Any] = {}
    try:
        version = _request_json(base_url, "/api/version", timeout)
        details["version"] = version.get("version")
        checks["serviceReachable"] = True

        tags = _request_json(base_url, "/api/tags", timeout)
        installed = sorted(
            {
                model_name
                for model in tags.get("models", [])
                for model_name in (model.get("name"), model.get("model"))
                if model_name
            }
        )
        details["installedModels"] = installed
        checks["llmInstalled"] = llm_model in installed
        checks["embeddingInstalled"] = embedding_model in installed
        if fallback_llm_model:
            checks["fallbackLlmInstalled"] = fallback_llm_model in installed

        generation = _request_json(
            base_url,
            "/api/generate",
            timeout,
            {
                "model": llm_model,
                "prompt": "只回答：健康",
                "stream": False,
                "keep_alive": 0,
            },
        )
        checks["generationWorks"] = bool(generation.get("response"))

        if fallback_llm_model:
            fallback_generation = _request_json(
                base_url,
                "/api/generate",
                timeout,
                {
                    "model": fallback_llm_model,
                    "prompt": "只回答：健康",
                    "stream": False,
                    "keep_alive": 0,
                },
            )
            checks["fallbackGenerationWorks"] = bool(
                fallback_generation.get("response")
            )

        embedding = _request_json(
            base_url,
            "/api/embed",
            timeout,
            {
                "model": embedding_model,
                "input": ["离线向量健康检查"],
                "keep_alive": 0,
            },
        )
        vectors = embedding.get("embeddings") or []
        checks["embeddingWorks"] = bool(vectors and vectors[0])
        details["embeddingDimensions"] = len(vectors[0]) if vectors else 0
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as err:
        details["error"] = f"{type(err).__name__}: {err}"
        checks.setdefault("serviceReachable", False)

    return {
        "success": bool(checks) and all(checks.values()),
        "baseUrl": base_url,
        "llmModel": llm_model,
        "fallbackLlmModel": fallback_llm_model,
        "embeddingModel": embedding_model,
        "checks": checks,
        "details": details,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--llm-model", required=True)
    parser.add_argument("--fallback-llm-model")
    parser.add_argument("--embedding-model", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=120)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be greater than zero")
    return args


def main() -> int:
    args = _parse_args()
    try:
        report = check_ollama(
            args.base_url,
            args.llm_model,
            args.embedding_model,
            args.timeout_seconds,
            args.fallback_llm_model,
        )
    except ValueError as err:
        print(json.dumps({"success": False, "error": str(err)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
