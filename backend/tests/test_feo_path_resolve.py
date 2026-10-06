"""Тест правила сопоставления (AE, AF, AG) с деревом ФЭО по пути — см. задание
06.10.2026 и docstring backend/scripts/fadm_sheet_load/feo_path_resolve.py.
Синтетическое дерево воспроизводит реальные находки прод-дерева «ФАДМ 2026_2»
(id 7320 локально / 89 на проде): длинное AF, одинаковое имя на двух уровнях
(«Техническое оснащение деятельности штаба» — и корень, и единственный
ребёнок), несколько «Не определена»."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fadm_sheet_load.feo_path_resolve import CategoryNode, FeoTree, resolve_feo_path  # noqa: E402

LONG_AF = (
    "3. Закупка комплекта форменной одежды для проведения торжественных мероприятий, "
    "направленных на гражданско-патриотическое воспитание молодого поколения, проведение "
    "занятий с различными категориями граждан, участие в ликвидации чрезвычайных ситуаций "
    "и их последствий, гуманитарных миссий и прочих"  # лист: «миссий» (прод-находка — дерево ниже «миссиях»)
)
TREE_AF_NAME = (
    "Закупка комплекта форменной одежды для проведения торжественных мероприятий, "
    "направленных на гражданско-патриотическое воспитание молодого поколения, проведение "
    "занятий с различными категориями граждан, участие в ликвидации чрезвычайных ситуаций "
    "и их последствий, гуманитарных миссиях и прочих"
)


def _build_tree() -> FeoTree:
    nodes = [
        # level 1 (корни)
        CategoryNode(1, None, "1. Техническое оснащение деятельности штаба", 1),
        CategoryNode(2, None, "Организация мероприятий", 1),
        CategoryNode(3, None, "Не определена", 1),
        # level 2
        CategoryNode(10, 1, "Техническое оснащение деятельности штаба", 2),  # то же имя, что у корня 1
        CategoryNode(20, 2, "Организация и проведение Слета студентов-спасателей", 2),
        CategoryNode(21, 2, TREE_AF_NAME, 2),
        CategoryNode(22, 2, "Не определена", 2),
        CategoryNode(23, 2, "Слёт студентов-спасателей", 2),
        # level 3 — дети "Техническое оснащение деятельности штаба" (id=10)
        CategoryNode(100, 10, "Бензин", 3),
        CategoryNode(101, 10, "Ремонт техники", 3),
        CategoryNode(102, 10, "Закупка компьютеров", 3),
        CategoryNode(103, 10, "Не определена", 3),
    ]
    return FeoTree(nodes)


def test_long_af_finds_truncated_tree_category():
    """AF в листе длиннее имени категории в дереве (лист не обрезан, дерево
    обрезано) — должен найтись узел 21 по префиксу, не корень 2."""
    tree = _build_tree()
    result = resolve_feo_path(tree, ae="2. Организация мероприятий", af=LONG_AF, ag="")
    assert result.category_id == 21
    assert result.stopped_at == "af"
    assert not result.ambiguous


def test_wordform_mismatch_found_by_common_prefix_among_siblings():
    """Реальная прод-находка (доп. правка 06.10.2026): AF листа оканчивается
    «...гуманитарных миссиЙ и прочих», имя категории дерева — «...гуманитарных
    миссиЯХ и прочих» (другое окончание слова у длинной 290-символьной
    строки) — ни exact, ни строгий prefix её не ловят (строки расходятся, а
    потом сходятся снова — это не отношение «одна строка — префикс другой»).
    Среди 4 детей AE (узлы 20/21/22/23) правильный узел (21) должен найтись
    третьим уровнем сравнения — общий префикс, который для него НАМНОГО
    длиннее, чем для остальных трёх братьев."""
    tree = _build_tree()
    af_with_wordform_mismatch = LONG_AF  # заканчивается "...миссий и прочих"
    result = resolve_feo_path(tree, ae="2. Организация мероприятий",
                               af=af_with_wordform_mismatch, ag="")
    assert result.category_id == 21
    assert result.stopped_at == "af"
    assert result.match_method == "common_prefix"
    assert not result.ambiguous


def test_common_prefix_near_tie_is_ambiguous():
    """Два ребёнка с ПОЧТИ одинаковым общим префиксом относительно AF листа
    (разница < COMMON_PREFIX_MARGIN=10 символов) — явного лидера нет, не
    угадываем, остаёмся на родителе и помечаем неоднозначность."""
    shared = "Закупка комплекта одежды для торжественных мероприятий организации клуба "
    nodes = [
        CategoryNode(1, None, "Направление", 1),
        CategoryNode(10, 1, shared + "Бета", 2),
        CategoryNode(11, 1, shared + "Гамма", 2),
    ]
    tree = FeoTree(nodes)
    result = resolve_feo_path(tree, ae="Направление", af=shared + "Альфа", ag="")
    assert result.category_id == 1  # остались на родителе (корне)
    assert result.stopped_at == "root"
    assert result.ambiguous
    assert result.ambiguous_level == "af"
    assert {c[0] for c in result.ambiguous_candidates} == {10, 11}


def test_ag_finds_grandchild_under_duplicate_name_level():
    """AE/AF совпадают с именем, которое повторяется на двух уровнях (корень 1
    и его ребёнок 10) — AF должен привести на уровень 2 (id=10), а AG —
    спуститься глубже, на уровень 3 (внук), а не остаться на дублирующемся
    имени верхнего уровня."""
    tree = _build_tree()
    result = resolve_feo_path(
        tree, ae="1. Техническое оснащение деятельности штаба",
        af="Техническое оснащение деятельности штаба", ag="Бензин",
    )
    assert result.category_id == 100
    assert result.stopped_at == "ag"
    assert result.path == [
        "1. Техническое оснащение деятельности штаба",
        "Техническое оснащение деятельности штаба",
        "Бензин",
    ]


def test_duplicate_name_on_two_levels_does_not_confuse_af_match():
    """Без AG (пусто) — AF сам по себе однозначно находит уровень 2 (id=10),
    не корень (id=1), хотя имена идентичны: поиск AF идёт СРЕДИ ДЕТЕЙ
    найденного по AE корня, а не глобально по всему дереву."""
    tree = _build_tree()
    result = resolve_feo_path(
        tree, ae="1. Техническое оснащение деятельности штаба",
        af="Техническое оснащение деятельности штаба", ag="",
    )
    assert result.category_id == 10
    assert result.stopped_at == "af"


def test_duplicate_na_names_resolved_by_path_not_globally():
    """«Не определена» встречается на всех трёх уровнях (id 3, 22, 103) —
    AE→AF→AG должны провести по ПУТИ до нужного уровня, не взять первую
    попавшуюся «Не определена» в дереве."""
    tree = _build_tree()
    result = resolve_feo_path(
        tree, ae="1. Техническое оснащение деятельности штаба",
        af="Техническое оснащение деятельности штаба", ag="Не определена",
    )
    assert result.category_id == 103
    assert result.stopped_at == "ag"


def test_ambiguous_match_stays_at_level_above():
    """AF короче обоих детей и — ЧИСТЫЙ префикс (без расхождений) ОБОИХ сразу
    (ни один из них не совпадает с AF ТОЧНО — иначе exact однозначно выиграл
    бы, это отдельный, более сильный уровень сравнения) — не угадываем,
    остаёмся на корне и сообщаем об неоднозначности."""
    nodes = [
        CategoryNode(1, None, "Направление", 1),
        CategoryNode(10, 1, "Закупка одежды для мероприятий организации", 2),
        CategoryNode(11, 1, "Закупка одежды для мероприятий организации клуба", 2),
    ]
    tree = FeoTree(nodes)
    result = resolve_feo_path(tree, ae="Направление", af="Закупка одежды для мероприятий", ag="")
    assert result.category_id == 1  # остались на корне
    assert result.stopped_at == "root"
    assert result.ambiguous
    assert result.ambiguous_level == "af"
    assert {c[0] for c in result.ambiguous_candidates} == {10, 11}


def test_exact_match_wins_over_prefix_ambiguity():
    """AF СОВПАДАЕТ ТОЧНО с одним из детей, хотя является также префиксом
    другого (более длинного) — exact (уровень 1) побеждает, это НЕ
    неоднозначность: длинное имя — явно другая, более широкая категория."""
    nodes = [
        CategoryNode(1, None, "Направление", 1),
        CategoryNode(10, 1, "Закупка одежды для мероприятий организации", 2),
        CategoryNode(11, 1, "Закупка одежды для мероприятий организации клуба", 2),
    ]
    tree = FeoTree(nodes)
    result = resolve_feo_path(tree, ae="Направление", af="Закупка одежды для мероприятий организации", ag="")
    assert result.category_id == 10
    assert result.match_method == "exact"
    assert not result.ambiguous


def test_af_not_found_falls_back_to_ag_global_when_unambiguous():
    """AF не совпал ни с одним прямым ребёнком AE, но AG однозначно находится
    среди всех потомков корня (включая уровень 3) — используем его, не
    остаёмся на корне просто так."""
    tree = _build_tree()
    result = resolve_feo_path(
        tree, ae="1. Техническое оснащение деятельности штаба",
        af="Совсем другое название, не найдётся нигде", ag="Ремонт техники",
    )
    assert result.category_id == 101
    assert result.stopped_at == "ag_global"


def test_af_found_as_grandchild_via_deep_search():
    """Прод-находка 07.10.2026 (владелец): папка для AF иногда заводится НЕ
    прямым ребёнком корня, а внуком (level 3) — «Приобретение ОСАГО для
    автомобилей» создана под «Техническое оснащение деятельности штаба»
    (level 2, сама дочь корня с тем же именем), хотя соответствует AF, а не
    AG. AF должен найтись глубоким поиском среди ВСЕХ потомков корня."""
    nodes = [
        CategoryNode(1, None, "1. Техническое оснащение деятельности штаба", 1),
        CategoryNode(10, 1, "Техническое оснащение деятельности штаба", 2),
        CategoryNode(100, 10, "Приобретение ОСАГО для автомобилей", 3),
    ]
    tree = FeoTree(nodes)
    result = resolve_feo_path(
        tree, ae="1. Техническое оснащение деятельности штаба",
        af="Приобретение ОСАГО для автомобилей", ag="",
    )
    assert result.category_id == 100
    assert result.stopped_at == "af_deep"
    assert result.match_method == "exact"
    assert not result.ambiguous


def test_af_deep_search_ambiguous_with_two_grandchildren():
    """Два внука с одинаковым именем под РАЗНЫМИ ветками одного корня — не
    угадываем, остаёмся на AE и помечаем уровень 'af_deep'."""
    nodes = [
        CategoryNode(1, None, "Направление", 1),
        CategoryNode(10, 1, "Ветка А", 2),
        CategoryNode(100, 10, "Приобретение ОСАГО для автомобилей", 3),
        CategoryNode(11, 1, "Ветка Б", 2),
        CategoryNode(101, 11, "Приобретение ОСАГО для автомобилей", 3),
    ]
    tree = FeoTree(nodes)
    result = resolve_feo_path(tree, ae="Направление", af="Приобретение ОСАГО для автомобилей", ag="")
    assert result.category_id == 1  # остались на корне
    assert result.stopped_at == "root"
    assert result.ambiguous
    assert result.ambiguous_level == "af_deep"
    assert {c[0] for c in result.ambiguous_candidates} == {100, 101}


def test_ae_not_found_returns_none():
    tree = _build_tree()
    result = resolve_feo_path(tree, ae="Направление, которого нет в дереве", af="что угодно", ag="")
    assert result.category_id is None
    assert result.stopped_at == "none"
