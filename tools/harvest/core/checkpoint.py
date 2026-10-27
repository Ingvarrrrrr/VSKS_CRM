"""Возобновление сбора по чекпоинту (jsonl). Файл `<out>.checkpoint.jsonl`
хранит построчно {"url", "kind", "status"} для каждого обработанного URL
(раздел/товар). --resume читает его через load_processed() и пропускает уже
встреченные URL; append_line() дописывает по одной строке по мере сбора,
чтобы прерванный прогон не терял прогресс."""
from __future__ import annotations

import json
import os
from pathlib import Path


def checkpoint_path(out_path: str) -> str:
    return f"{out_path}.checkpoint.jsonl"


def append_line(path: str, url: str, kind: str, status: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"url": url, "kind": kind, "status": status}, ensure_ascii=False) + "\n")


def load_processed(path: str) -> set[str]:
    """Множество URL, уже встречавшихся в чекпоинте (любой kind/status).
    Файла нет → пустое множество."""
    if not os.path.exists(path):
        return set()
    processed: set[str] = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = row.get("url")
            if url:
                processed.add(url)
    return processed
