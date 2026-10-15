"""Приёмочные тесты (владелец, 15.10.2026): «нужны в дательном падеже
переменные подписанта и ФИО» — пример: «Председателю Совета Донецкого РО
ВСКС Артеевой Анне Игоревне».

Доработка (15.10.2026, тот же день): найден баг в РОДИТЕЛЬНОМ —
_to_gen_phrase("Председатель Совета Донецкого РО ВСКС") пословно давало
«Председателя Совета Донецкого Ро Вскса» (склонялись уже-родительные слова
и аббревиатуры). ПРАВИЛО №6: один алгоритм разбора головной группы
должности — _to_case_position(phrase, case) — на оба падежа;
_to_gen_phrase/_to_dat_position теперь тонкие обёртки над ним.

Офлайн, без БД и сети. ПРАВИЛО №6: _to_case_fio/_to_dat_fio/_to_dat_fio_initials
— единственный расчёт склонения ФИО; _to_case_position — единственный
расчёт склонения должности (родительный и дательный), см. morphology.py.
"""
from app.services.documents.morphology import (
    _to_gen_fio,
    _to_gen_phrase,
    _to_dat_fio,
    _to_dat_fio_initials,
    _to_dat_position,
)


# ── Должность в родительном — головная группа, не пословно (регресс бага) ──

def test_position_genitive_chairman_with_long_tail_not_mangled():
    assert _to_gen_phrase("Председатель Совета Донецкого РО ВСКС") == \
        "Председателя Совета Донецкого РО ВСКС"


def test_position_genitive_general_director():
    assert _to_gen_phrase("Генеральный директор") == "Генерального директора"


def test_position_genitive_president():
    assert _to_gen_phrase("Президент") == "Президента"


def test_position_genitive_department_head():
    assert _to_gen_phrase("Начальник отдела снабжения") == "Начальника отдела снабжения"


def test_position_genitive_acting_head_participle_stops_at_object():
    assert _to_gen_phrase("Исполняющий обязанности директора") == \
        "Исполняющего обязанности директора"


def test_position_genitive_lowercase_specialist():
    assert _to_gen_phrase("главный специалист") == "главного специалиста"


def test_position_genitive_director_legal_affairs():
    assert _to_gen_phrase("Директор по правовым вопросам") == \
        "Директора по правовым вопросам"


# ── Должность — только головная группа, не пословно ────────────────────────

def test_position_dative_chairman_with_long_tail():
    assert _to_dat_position("Председатель Совета Донецкого РО ВСКС") == \
        "Председателю Совета Донецкого РО ВСКС"


def test_position_dative_general_director():
    assert _to_dat_position("Генеральный директор") == "Генеральному директору"


def test_position_dative_president():
    assert _to_dat_position("Президент") == "Президенту"


def test_position_dative_director():
    assert _to_dat_position("Директор") == "Директору"


def test_position_dative_acting_head_participle_stops_at_object():
    assert _to_dat_position("Исполняющий обязанности директора") == \
        "Исполняющему обязанности директора"


def test_position_dative_chairman_alone():
    assert _to_dat_position("Председатель") == "Председателю"


def test_position_dative_empty_string():
    assert _to_dat_position("") == ""


# ── ФИО в дательном падеже ──────────────────────────────────────────────────

def test_fio_dative_female():
    assert _to_dat_fio("Артеева Анна Игоревна") == "Артеевой Анне Игоревне"


def test_fio_dative_male():
    assert _to_dat_fio("Козеев Евгений Викторович") == "Козееву Евгению Викторовичу"


def test_fio_dative_foreign_name_not_truncated():
    # Иностранное/неклассическое ФИО — не выдумываем падеж, возвращаем как есть
    assert _to_dat_fio("Дефассье Лоран, Луи, Клод") == "Дефассье Лоран, Луи, Клод"


def test_fio_dative_initials():
    assert _to_dat_fio_initials("Артеева Анна Игоревна") == "Артеевой А.И."


# ── Регресс: _to_gen_fio не изменился после обобщения в _to_case_fio ───────

def test_gen_fio_regression_unchanged():
    assert _to_gen_fio("Козеев Евгений Викторович") == "Козеева Евгения Викторовича"
