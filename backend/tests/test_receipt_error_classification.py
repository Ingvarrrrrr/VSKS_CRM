"""Независимая приёмка (2026-09-17, п.7): покрытие classify_proverkacheka_error().

app/services/receipts_parsing.py::classify_proverkacheka_error разбирает текст
ошибки proverkacheka.com/ФНС на три ветки: лимит запросов (429), чек в
обработке до 24 часов (409), чек не найден (400).

КРИТИЧНАЯ регрессия, которую тест обязан закрепить: сообщение «чек уже
находится в обработке» содержит слово «уже» — раньше (до узкого совпадения
"превышен(о)" + "запрос"/"обращен"/"лимит") оно ложно попадало в ветку
FNS_RATE_LIMIT вместо RECEIPT_PENDING. Текущая реализация матчит is_rate_limit
ТОЛЬКО на связку «превышен(о)» + «запрос/обращен/лимит» — «уже» само по себе
теперь относится к pending_markers.
"""
from app.services.receipts_parsing import classify_proverkacheka_error


def test_rate_limit_branch():
    result = classify_proverkacheka_error("Превышено количество запросов с данного токена")
    assert result["status"] == 429
    assert result["code"] == "FNS_RATE_LIMIT"


def test_rate_limit_branch_alternate_wording():
    result = classify_proverkacheka_error("Превышен лимит обращений, попробуйте позже")
    assert result["status"] == 429
    assert result["code"] == "FNS_RATE_LIMIT"


def test_pending_branch_24h_wording():
    result = classify_proverkacheka_error("Данные по чеку недоступны, обработка занимает до 24 часов")
    assert result["status"] == 409
    assert result["code"] == "RECEIPT_PENDING"


def test_not_found_branch_with_message():
    result = classify_proverkacheka_error("Чек с указанными реквизитами не найден")
    assert result["status"] == 400
    assert result["code"] == "RECEIPT_NOT_FOUND"
    assert "не найден" in result["message"] or "Чек не найден" in result["message"]


def test_not_found_branch_empty_message():
    result = classify_proverkacheka_error("")
    assert result["status"] == 400
    assert result["code"] == "RECEIPT_NOT_FOUND"
    assert result["hint"] is None


def test_regression_already_in_processing_is_pending_not_rate_limit():
    """РЕГРЕССИЯ: «чек уже находится в обработке» содержит «уже», но НЕ
    «превышен(о)» — обязана классифицироваться как RECEIPT_PENDING (409),
    а не FNS_RATE_LIMIT (429). До фикса is_rate_limit матчил само слово «уже»
    и здесь ложно возвращал бы 429."""
    result = classify_proverkacheka_error("Чек уже находится в обработке, попробуйте позже")
    assert result["code"] == "RECEIPT_PENDING"
    assert result["status"] == 409
    assert result["code"] != "FNS_RATE_LIMIT"


def test_regression_already_in_processing_alternate_wording():
    result = classify_proverkacheka_error("Данный чек уже обрабатывается ФНС")
    assert result["code"] == "RECEIPT_PENDING"
    assert result["status"] == 409
