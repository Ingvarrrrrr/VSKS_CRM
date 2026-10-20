"""Безопасная проверка внешнего URL перед скачиванием по ссылке пользователя
(SSRF-гейт, Правило №6 — один источник для ВСЕХ мест, где бэкенд качает файл
по URL, который ввёл пользователь).

Аудит безопасности 2026-10-20: `product_photo_fetch.py` качал фото товара по
ссылке пользователя голым `urllib.request.urlopen` без каких-либо проверок
адреса — ссылка вида `http://127.0.0.1:8000/...`, `http://172.17.0.1/...`,
`http://10.0.0.5/...`, `http://169.254.169.254/latest/meta-data/...` (облачный
metadata-эндпоинт) или внутреннее docker-имя (`db`, `n8n`, `backend_b`) били
во внутреннюю сеть от имени сервера. Тот же паттерн — выгрузка заявки в Excel
(`routers/wish_export.py`), которая тоже качает `product.photo_url`/`photo_link`
по ссылке пользователя.

Правила:
  - схема только http/https;
  - хост резолвится через DNS, И ЛЮБОЙ из полученных адресов — приватный/
    loopback/link-local/reserved/multicast/unspecified → отказ (не только
    первый адрес: DNS rebinding / multi-A-record обход одной проверки);
  - голое имя без точки (внутреннее docker-имя вроде `db`, `n8n`, `backend_b`)
    запрещено даже если бы как-то зарезолвилось — у таких имён в принципе нет
    публичного смысла;
  - редиректы проверяющий код проводит САМ (urllib/httpx с ручным переходом),
    каждая цель редиректа — через этот же хелпер, не больше MAX_REDIRECTS.

Внешние API с фиксированным адресом (ФНС/proverkacheka, Фабрикант, DaData,
Telegram, Я.Диск/Google Drive API) сюда не заворачиваются — это НЕ ссылки
пользователя, адрес задан в коде.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

MAX_REDIRECTS = 5


class UnsafeUrlError(Exception):
    """URL отклонён SSRF-гейтом. `reason` — машинный код для логов/ответа."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


def _is_private_address(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return True  # не распарсился как IP — считаем небезопасным, не пропускаем
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def resolve_all_addresses(host: str) -> list[str]:
    """Все A/AAAA-адреса хоста. Пустой список/исключение резолвера → UnsafeUrlError
    (не пропускаем «не удалось проверить» как «безопасно»)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise UnsafeUrlError("dns_error", f"Не удалось определить адрес хоста: {e}") from e
    addrs = {info[4][0] for info in infos if info and info[4]}
    if not addrs:
        raise UnsafeUrlError("dns_error", "Хост не резолвится")
    return list(addrs)


def assert_safe_url(url: str) -> None:
    """Бросает UnsafeUrlError, если `url` может достучаться до внутренней сети.

    Вызывать для КАЖДОЙ цели — исходного URL и каждого шага редиректа."""
    parts = urlsplit(url)
    scheme = (parts.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise UnsafeUrlError("scheme", f"Недопустимая схема ссылки: {scheme or '—'}")

    host = parts.hostname
    if not host:
        raise UnsafeUrlError("no_host", "В ссылке не указан хост")

    # Голое docker-имя без точки (db, n8n, backend_b, localhost) — запрещаем
    # сразу, не дожидаясь резолва: даже если это публичный однословный домен
    # (бывает), для ссылок пользователя на фото/файл легитимной причины нет.
    if "." not in host and host.lower() != "localhost":
        host_literal_ip = True
        try:
            ipaddress.ip_address(host)
        except ValueError:
            host_literal_ip = False
        if not host_literal_ip:
            raise UnsafeUrlError("bare_hostname", f"Недопустимое имя хоста: {host}")
    if host.lower() == "localhost":
        raise UnsafeUrlError("localhost", "Ссылка на localhost запрещена")

    for addr in resolve_all_addresses(host):
        if _is_private_address(addr):
            raise UnsafeUrlError(
                "private_address",
                f"Ссылка указывает на внутренний/приватный адрес ({addr})",
            )
