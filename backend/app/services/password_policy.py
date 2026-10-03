"""Политика нового пароля — ЕДИНСТВЕННЫЙ источник правил (Правило №6).

Вызывать отсюда везде, где пользователь или админ ЗАДАЁТ новый пароль:
регистрация, сброс по ссылке, смена своего, админ создаёт/меняет чужой,
импорт сотрудников. НЕ проверяет уже существующие хэши — только то, что
кто-то пытается установить ПРЯМО СЕЙЧАС. Не плодить второй набор правил —
если нужна дополнительная проверка, добавлять сюда.
"""
from typing import Iterable, Optional

from fastapi import HTTPException

MIN_LENGTH = 8

# ~100 самых частых паролей по утечкам (RockYou/SecLists и рунет-специфика) —
# сравнение без учёта регистра, см. _normalize.
COMMON_PASSWORDS = {
    "123456", "12345678", "123456789", "1234567890", "12345",
    "qwerty", "password", "111111", "11111111", "123123",
    "abc123", "qwerty123", "1q2w3e4r", "йцукен", "qwertyuiop",
    "1234567", "000000", "iloveyou", "admin", "admin123",
    "letmein", "welcome", "monkey", "dragon", "football",
    "baseball", "master", "superman", "trustno1", "sunshine",
    "princess", "qwe123", "password1", "password123", "passw0rd",
    "1qaz2wsx", "zaq12wsx", "qazwsx", "qweasd", "asdfgh",
    "asdasd", "123qwe", "qwerty1", "qwerty12", "1234",
    "12345678910", "0000000", "123321", "654321", "7777777",
    "1111111", "88888888", "121212", "222222", "aaaaaa",
    "1q2w3e", "1qazxsw2", "zxcvbnm", "zxcvbn", "a123456",
    "fuckyou", "whatever", "123456a", "666666", "qazwsxedc",
    "pokemon", "qwerty12345", "qwertyui", "starwars", "login",
    "qweqwe", "123123123", "aa123456", "qwerty123456", "parol",
    "parol123", "qwer1234", "123abc", "1234qwer", "lolkek",
    "guest", "test", "test123", "user123", "temp1234",
    "changeme", "default1", "root1234", "pass1234", "pass123",
    "secret12", "iloveyou1", "hello123", "flower1", "sunshine1",
    "shadow12", "mustang1", "access12", "batman12", "nikita123",
    "sergey123", "maxim123", "vladimir1", "andrey123", "oleg1234",
    "1234561", "zxcasdqwe", "q1w2e3r4", "p@ssw0rd", "p@ssword",
}


def _normalize(value: str) -> str:
    return (value or "").strip().lower()


def validate_new_password(password: str, identifiers: Optional[Iterable[Optional[str]]] = None) -> None:
    """Raises HTTPException(422, ...) если пароль не проходит политику.

    identifiers — email/логин владельца пароля (пароль не должен им равняться).
    """
    pw = password or ""
    if len(pw) < MIN_LENGTH:
        raise HTTPException(422, f"Пароль слишком короткий: минимум {MIN_LENGTH} символов")

    norm_pw = _normalize(pw)
    if norm_pw in COMMON_PASSWORDS:
        raise HTTPException(
            422,
            "Этот пароль слишком распространён и легко подбирается. Выберите другой",
        )

    for ident in (identifiers or []):
        if ident and norm_pw == _normalize(ident):
            raise HTTPException(422, "Пароль не должен совпадать с email или логином")
