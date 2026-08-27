"""Validate the bundled cl100k_base tokenizer cache without network access."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Dict

CACHE_FILENAME = "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
CACHE_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_cache(cache_dir: Path) -> Dict[str, object]:
    cache_dir = cache_dir.expanduser().resolve()
    cache_file = cache_dir / CACHE_FILENAME
    errors = []
    if not cache_file.is_file():
        errors.append(f"Missing tokenizer cache file: {cache_file}")
    elif _sha256(cache_file) != CACHE_SHA256:
        errors.append(f"Tokenizer cache file is invalid: {cache_file}")

    token_count = None
    if not errors:
        os.environ["TIKTOKEN_CACHE_DIR"] = str(cache_dir)
        try:
            import tiktoken

            encoding = tiktoken.get_encoding("cl100k_base")
            token_count = len(encoding.encode("离线中文数据分析"))
        except Exception as error:
            errors.append(f"Cannot load cl100k_base from offline cache: {error}")

    return {
        "success": not errors,
        "cacheDir": str(cache_dir),
        "cacheFile": str(cache_file),
        "tokenCount": token_count,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    args = parser.parse_args()
    report = check_cache(args.cache_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
