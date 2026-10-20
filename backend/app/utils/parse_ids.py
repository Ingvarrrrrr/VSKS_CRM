"""app/utils/parse_ids.py — разбор query-параметра "через запятую" с id'ами
(subsidy_ids=1,2,3) — ОДНА точка разбора (ПРАВИЛО №6).

Повод (находка С4, tests/behavior/REPORT.md): одна и та же логика
`[int(x) for x in subsidy_ids.split(",") if x.strip()]` была скопирована в
dashboard_analytics.py, dashboard_redistributable_drill.py,
dashboard_metric_drill.py, dashboard_contracts_drill.py,
dashboard_type_drill.py, dashboard_paid_over_delivered_drill.py — мусорный
ввод (`?subsidy_ids=null`, `?subsidy_ids=abc`) падал в `int("null")` →
голый ValueError → 500 вместо честного 422. Теперь мусор ловится здесь ОДИН
раз и отдаётся как `HTTPException(422, ...)` с понятным текстом (формат
совпадает с остальными обработчиками — см. app/errors.py
http_exception_handler, который разворачивает dict-detail с code/message)."""
from typing import Optional

from fastapi import HTTPException


def parse_id_list(raw: Optional[str], *, param_name: str = "subsidy_ids") -> Optional[list[int]]:
    """'1,2,3' → [1,2,3]; пусто/None → None. Мусор (нечисло) → HTTPException 422,
    не ValueError/500."""
    if not raw:
        return None
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "INVALID_PARAM_VALUE",
                    "message": f"Параметр «{param_name}»: «{part}» не является числом",
                },
            )
    return out or None


def parse_id_set(raw: Optional[str], *, param_name: str = "subsidy_ids") -> Optional[set]:
    """Та же разбор, что parse_id_list, но возвращает set — нужен drill-роутерам
    (dashboard_*_drill.py), где раньше была своя копия `_parse_subsidy_ids`."""
    ids = parse_id_list(raw, param_name=param_name)
    return set(ids) if ids is not None else None
