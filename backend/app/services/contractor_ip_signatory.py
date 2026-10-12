"""Подписант для ИП при поиске по ИНН в ЕГРИП (Корректировки GALA 12.10, п.1).

Причина: `lookup_inn` (app/routers/contractors_lookup.py) берёт подписанта из
поля руководителя ответа ФНС ("g") — у ИП этого поля нет, подписант оставался
пустым. Для ИП подписант — сам предприниматель: ФИО разбирается из названия
(которое ЕГРИП отдаёт как "ИП Фамилия Имя Отчество" или просто ФИО), должность
фиксированная «Индивидуальный предприниматель», основание — его ОГРНИП.

Единственное место этой логики (ПРАВИЛО №6) — вызывается только из lookup_inn
для 12-значного ИНН; второй разбор ФИО ИП в проекте не заводить.
"""
import re

from app.services.fio import split_fio

# Префиксы, которыми ЕГРИП иногда предваряет ФИО предпринимателя в названии
# ("ИП Борисов Борис Викторович", "Индивидуальный предприниматель Борисов...").
_IP_PREFIX_RE = re.compile(
    r"^\s*(индивидуальный\s+предприниматель|ип)\b[.,:]?\s*",
    re.IGNORECASE,
)


def _strip_ip_prefix(name: str | None) -> str | None:
    if not name:
        return None
    return _IP_PREFIX_RE.sub("", name.strip()).strip() or None


def resolve_ip_signatory(name: str | None, ogrnip: str | None) -> dict:
    """Подписант-ИП из наименования ЕГРИП.

    `name` — наименование контрагента (как его отдаёт ЕГРИП, возможно с
    префиксом «ИП »/«Индивидуальный предприниматель »); `ogrnip` — ОГРНИП
    (в ответе ЕГРИП это то же поле "o", что ОГРН у юрлиц).

    Возвращает только signatory_last/first/middle_name, signatory_position,
    signatory_basis — остальные поля (включая director_*) не трогает, их
    заполняет вызывающий как раньше.
    """
    fio = _strip_ip_prefix(name)
    last, first, middle = split_fio(fio)
    basis = f"ОГРНИП № {ogrnip.strip()}" if ogrnip and ogrnip.strip() else None
    return {
        "signatory_last_name": last,
        "signatory_first_name": first,
        "signatory_middle_name": middle,
        "signatory_position": "Индивидуальный предприниматель",
        "signatory_basis": basis,
    }
