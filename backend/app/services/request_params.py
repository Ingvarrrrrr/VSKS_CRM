"""Общий (не только ФЭО) механизм: параметры импорта принимаются либо из
query-строки (старое поведение, оставлено для обратной совместимости —
на проде в PWA-кеше может задержаться старый фронт), либо — приоритетно —
из тела multipart-формы того же запроса, которым уже идёт сам файл.

Баг владельца 2026-09-17: импорт в субсидию "Центрпоиск_3" падал с HTTP 414
(URI Too Long) — фронт (`useFeoImport.ts`) собирал ~70 параметров `col_*` +
`remap` + `duplicate_resolutions` (JSON с кириллическими ключами конфликтов
по КАЖДОЙ категории) в query-строку POST-запроса, а файл шёл отдельно телом
FormData. На крупной субсидии URL уходил на десятки КБ — свыше лимита
nginx (`large_client_header_buffers`, дефолт 8 КБ). Тот же дефект, меньшего
масштаба, — `useItemsImport.ts` (`resolutions` при импорте позиций закупки).

Правило №6 (один источник истины): вместо ветвления «Query или Form» в
каждом из ~70 параметров — ОДНО место, разбирающее multipart-форму и
подменяющее значения, уже разобранные FastAPI из Query. Роутеры продолжают
объявлять параметры как `Query(...)` (иначе OpenAPI/старый фронт сломались
бы) — этот хелпер только ПЕРЕОПРЕДЕЛЯЕТ уже полученные значения, если то же
имя поля пришло и в форме.
"""
from fastapi import Request

TRUE_STRINGS = {"true", "1", "yes", "on"}


async def merge_form_over_query(
    request: Request,
    query_values: dict,
    *,
    bool_fields: frozenset[str] = frozenset(),
    int_fields: frozenset[str] = frozenset(),
) -> dict:
    """Возвращает копию `query_values`, где значение каждого поля заменено
    на одноимённое поле multipart-формы текущего запроса, если оно там
    присутствует и непусто. Поле, отсутствующее в форме (старый фронт,
    слал только через query), оставляет значение, уже разобранное FastAPI
    из Query — обратная совместимость гарантирована по построению, а не
    отдельной веткой на каждый параметр.

    `bool_fields`/`int_fields` — имена полей, которые нужно привести к
    bool/int (form всегда отдаёт str); всё остальное остаётся строкой.
    Пустая строка в форме («не выбрано») не подменяет значение из query —
    так же, как FastAPI Query с дефолтом ведёт себя при отсутствии параметра.
    """
    try:
        form = await request.form()
    except Exception:
        return dict(query_values)
    if not form:
        return dict(query_values)

    merged = dict(query_values)
    for key in merged:
        if key not in form:
            continue
        raw = form.get(key)
        if raw is None:
            continue
        raw_str = str(raw)
        if raw_str == "":
            continue
        if key in bool_fields:
            merged[key] = raw_str.strip().lower() in TRUE_STRINGS
        elif key in int_fields:
            try:
                merged[key] = int(raw_str)
            except ValueError:
                continue
        else:
            merged[key] = raw_str
    return merged
