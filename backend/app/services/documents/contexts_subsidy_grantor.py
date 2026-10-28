"""Переменные субсидии-грантодателя для документов — единственный расчёт
(ПРАВИЛО №6).

До этого файла набор ключей `subsidy_grantor_name` / `subsidy_grantor_name_instrumental`
/ `subsidy_ministry_name` собирался ДВАЖДЫ с разной логикой творительного падежа:
- `contexts_extra.py::add_phase28_context` — через `doc_case_org_name_case(..., 'ablt')`
  (нормализация капса + склонение головной группы);
- `fabrikant_package.py` (генерация пакета для Фабриканта) — через отдельную
  `_to_ablt_org_name` (contexts_org_people.py), БЕЗ нормализации капса.

Владелец (28.10.2026): нужен ещё родительный падеж и грантодателя, и
министерства — `{{subsidy_grantor_name_gen}}` / `{{subsidy_ministry_name_gen}}`.
Вместо третьей копии — один модуль, вызывается из обоих мест.
"""
from app.services.documents.org_name_case import doc_case_org_name, doc_case_org_name_case


def build_subsidy_grantor_context(subsidy) -> dict:
    """Ключи субсидии-грантодателя для контекста документа. NULL-safe:
    `subsidy=None` или пустые поля карточки субсидии → пустые строки везде.

    - `subsidy_grantor_name` — именительный падеж, регистр нормализован
      (см. `doc_case_org_name`, как Заказчик/Исполнитель).
    - `subsidy_grantor_name_instrumental` / `subsidy_grantor_name_gen` —
      творительный/родительный падеж через `doc_case_org_name_case`
      (нормализация регистра → склонение головной группы, ПРАВИЛО №6 —
      единственный склонятель, тот же, что и для Заказчика/Исполнителя).
    - `subsidy_ministry_name` — как есть (поведение не менялось, министерство
      в карточке и так пишется нормальным регистром).
    - `subsidy_ministry_name_gen` — тот же склонятель, что и выше.
    """
    grantor_raw = (subsidy.grantor_name or "").strip() if subsidy else ""
    ministry_raw = (subsidy.ministry_name or "").strip() if subsidy else ""
    return {
        "subsidy_grantor_name": doc_case_org_name(grantor_raw, []),
        "subsidy_grantor_name_instrumental": doc_case_org_name_case(grantor_raw, [], 'ablt'),
        "subsidy_grantor_name_gen": doc_case_org_name_case(grantor_raw, [], 'gent'),
        "subsidy_ministry_name": ministry_raw,
        "subsidy_ministry_name_gen": doc_case_org_name_case(ministry_raw, [], 'gent'),
    }
