"""Тест подписанта ИП (Корректировки GALA 12.10, п.1) — без сети.

resolve_ip_signatory разбирает ФИО из наименования ЕГРИП и собирает
основание из ОГРНИП. Реальный пример владельца: ИНН 616501044877,
«Борисов Борис Викторович», ОГРНИП 304616536600450.
"""
from app.services.contractor_ip_signatory import resolve_ip_signatory


def test_ip_signatory_from_plain_fio():
    res = resolve_ip_signatory("Борисов Борис Викторович", "304616536600450")
    assert res["signatory_last_name"] == "Борисов"
    assert res["signatory_first_name"] == "Борис"
    assert res["signatory_middle_name"] == "Викторович"
    assert res["signatory_position"] == "Индивидуальный предприниматель"
    assert res["signatory_basis"] == "ОГРНИП № 304616536600450"


def test_ip_signatory_strips_ip_prefix():
    res = resolve_ip_signatory("ИП Борисов Борис Викторович", "304616536600450")
    assert res["signatory_last_name"] == "Борисов"
    assert res["signatory_first_name"] == "Борис"
    assert res["signatory_middle_name"] == "Викторович"


def test_ip_signatory_strips_full_prefix_case_insensitive():
    res = resolve_ip_signatory("индивидуальный предприниматель Иванов Иван Иванович", None)
    assert res["signatory_last_name"] == "Иванов"
    assert res["signatory_basis"] is None


def test_ip_signatory_empty_name():
    res = resolve_ip_signatory(None, "123")
    assert res["signatory_last_name"] is None
    assert res["signatory_first_name"] is None
    assert res["signatory_middle_name"] is None
    assert res["signatory_basis"] == "ОГРНИП № 123"
