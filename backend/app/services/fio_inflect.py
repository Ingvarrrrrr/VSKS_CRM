"""Модуль склонения русских ФИО и должностей в 5 косвенных падежей (Правило №6).

Чистый детерминированный модуль без внешних зависимостей (< 300 строк).
Падежи: gent (род.), datv (дат.), accs (вин.), ablt (твор.), loct (предл.).
"""
from __future__ import annotations

import re
from typing import Optional

_VELAR_SH_ENDINGS = ("га", "ка", "ха", "жа", "ша", "ча", "ща")
_NON_DECLINING_SURNAME_ENDINGS = (
    "ко", "енко", "о", "е", "э", "и", "ы", "у", "ю",
    "ых", "их", "дзе", "швили", "иа", "уа",
)
_FEMALE_SURNAME_SUFFIXES = ("ова", "ева", "ина", "ына", "ская", "цкая", "ая", "яя")
_INITIALS_PATTERN = re.compile(r"^[А-ЯA-ZЁ]\.(?:[А-ЯA-ZЁ]\.)?$")


def is_patronymic(word: str) -> bool:
    w = word.lower().rstrip(",")
    return w.endswith(("вич", "вна", "чна", "ична"))


def detect_gender(surname: str, name: str = "", patronymic: str = "") -> str:
    p = patronymic.lower()
    if p.endswith(("вна", "чна", "ична")):
        return "female"
    if p.endswith(("вич", "ич")):
        return "male"

    s = surname.lower()
    if s.endswith(_FEMALE_SURNAME_SUFFIXES):
        return "female"
    if s.endswith(("ов", "ев", "ин", "ын", "ский", "цкий", "ый", "ий")):
        return "male"

    n = name.lower()
    if n in ("илья", "никита", "лука", "фока", "кузьма", "данила"):
        return "male"
    if n.endswith(("а", "я", "ия", "ь")):
        return "female"
    return "male"


def decline_surname(surname: str, case: str = "gent", gender: Optional[str] = None) -> str:
    if not surname:
        return ""
    low = surname.lower()
    if low.endswith(_NON_DECLINING_SURNAME_ENDINGS):
        return surname

    gen = gender or ("female" if low.endswith(_FEMALE_SURNAME_SUFFIXES) else "male")
    is_cap = surname[0].isupper()

    if gen == "female":
        if not low.endswith(("а", "я")):
            return surname
        if low.endswith(("ская", "цкая")):
            suff = "ую" if case == "accs" else "ой"
            res = low[:-2] + suff
        elif low.endswith(("ова", "ева", "ина", "ына")):
            suff = "у" if case == "accs" else "ой"
            res = low[:-1] + suff
        elif low.endswith(("ая", "яя")):
            suff = "ую" if case == "accs" else "ой"
            res = low[:-2] + suff
        elif low.endswith(_VELAR_SH_ENDINGS):
            suff = "и" if case == "gent" else ("е" if case in ("datv", "loct") else ("у" if case == "accs" else "ой"))
            res = low[:-1] + suff
        else:
            suff = "ы" if case == "gent" else ("е" if case in ("datv", "loct") else ("у" if case == "accs" else "ой"))
            res = low[:-1] + suff
    else:  # male
        if low.endswith(("ский", "цкий")):
            suff = "ого" if case in ("gent", "accs") else ("ому" if case == "datv" else ("ом" if case == "loct" else "им"))
            res = low[:-2] + suff
        elif low.endswith(("ый", "ой")):
            suff = "ого" if case in ("gent", "accs") else ("ому" if case == "datv" else ("ом" if case == "loct" else "ым"))
            res = low[:-2] + suff
        elif low.endswith(("ов", "ев", "ин", "ын")):
            suff = "а" if case in ("gent", "accs") else ("у" if case == "datv" else ("е" if case == "loct" else "ым"))
            res = low + suff
        elif low.endswith("ь"):
            suff = "я" if case in ("gent", "accs") else ("ю" if case == "datv" else ("е" if case == "loct" else "ем"))
            res = low[:-1] + suff
        elif low.endswith(_VELAR_SH_ENDINGS):
            suff = "и" if case == "gent" else ("е" if case in ("datv", "loct") else ("у" if case == "accs" else "ой"))
            res = low[:-1] + suff
        elif low.endswith("а"):
            suff = "ы" if case == "gent" else ("е" if case in ("datv", "loct") else ("у" if case == "accs" else "ой"))
            res = low[:-1] + suff
        elif low.endswith("я"):
            suff = "и" if case == "gent" else ("е" if case in ("datv", "loct") else ("ю" if case == "accs" else "ей"))
            res = low[:-1] + suff
        else:  # consonant
            suff = "а" if case in ("gent", "accs") else ("у" if case == "datv" else ("е" if case == "loct" else "ом"))
            res = low + suff

    return res.capitalize() if is_cap else res


def decline_first_name(name: str, case: str = "gent", gender: Optional[str] = None) -> str:
    if not name:
        return ""
    low = name.lower()
    is_cap = name[0].isupper()
    gen = gender or ("male" if low in ("илья", "никита", "лука", "фока") or not low.endswith(("а", "я", "ь")) else "female")

    if gen == "female":
        if low.endswith("ия"):
            suff = "ию" if case == "accs" else ("ией" if case == "ablt" else "ии")
            res = low[:-2] + suff
        elif low.endswith(_VELAR_SH_ENDINGS):
            suff = "и" if case == "gent" else ("е" if case in ("datv", "loct") else ("у" if case == "accs" else "ой"))
            res = low[:-1] + suff
        elif low.endswith("а"):
            suff = "ы" if case == "gent" else ("е" if case in ("datv", "loct") else ("у" if case == "accs" else "ой"))
            res = low[:-1] + suff
        elif low.endswith("я"):
            suff = "и" if case == "gent" else ("е" if case in ("datv", "loct") else ("ю" if case == "accs" else "ей"))
            res = low[:-1] + suff
        elif low.endswith("ь"):
            suff = "и" if case in ("gent", "datv", "loct") else ("ь" if case == "accs" else "ью")
            res = low[:-1] + suff
        else:
            res = low
    else:  # male
        if low in ("илья",):
            suff = "и" if case == "gent" else ("е" if case in ("datv", "loct") else ("ю" if case == "accs" else "ёй"))
            res = low[:-1] + suff
        elif low.endswith(_VELAR_SH_ENDINGS):
            suff = "и" if case == "gent" else ("е" if case in ("datv", "loct") else ("у" if case == "accs" else "ой"))
            res = low[:-1] + suff
        elif low.endswith("а"):
            suff = "ы" if case == "gent" else ("е" if case in ("datv", "loct") else ("у" if case == "accs" else "ой"))
            res = low[:-1] + suff
        elif low.endswith("ий"):
            suff = "ия" if case in ("gent", "accs") else ("ию" if case == "datv" else ("ии" if case == "loct" else "ием"))
            res = low[:-2] + suff
        elif low.endswith(("ей", "ай", "ой")):
            suff = "я" if case in ("gent", "accs") else ("ю" if case == "datv" else ("е" if case == "loct" else "ем"))
            res = low[:-1] + suff
        elif low.endswith("ь"):
            suff = "я" if case in ("gent", "accs") else ("ю" if case == "datv" else ("е" if case == "loct" else "ем"))
            res = low[:-1] + suff
        else:
            suff = "а" if case in ("gent", "accs") else ("у" if case == "datv" else ("е" if case == "loct" else "ом"))
            res = low + suff

    return res.capitalize() if is_cap else res


def decline_patronymic(patronymic: str, case: str = "gent") -> str:
    if not patronymic:
        return ""
    low = patronymic.lower()
    is_cap = patronymic[0].isupper()

    if low.endswith(("овна", "евна", "ична", "чна")):
        suff = "ы" if case == "gent" else ("е" if case in ("datv", "loct") else ("у" if case == "accs" else "ой"))
        res = low[:-1] + suff
    elif low.endswith(("ович", "евич", "ич")):
        suff = "а" if case in ("gent", "accs") else ("у" if case == "datv" else ("е" if case == "loct" else "ем"))
        res = low + suff
    else:
        res = low

    return res.capitalize() if is_cap else res


def inflect_fio(full_name: str, case: str = "gent") -> str:
    if not full_name or not full_name.strip():
        return full_name or ""

    parts = full_name.strip().split()
    if not parts:
        return ""

    if len(parts) == 2 and _INITIALS_PATTERN.match(parts[0]):
        decl_s = decline_surname(parts[1], case=case)
        return f"{parts[0]} {decl_s}"

    if len(parts) == 2 and _INITIALS_PATTERN.match(parts[1]):
        decl_s = decline_surname(parts[0], case=case)
        return f"{decl_s} {parts[1]}"

    if len(parts) >= 3 and is_patronymic(parts[2]):
        gender = detect_gender(parts[0], parts[1], parts[2])
        s = decline_surname(parts[0], case=case, gender=gender)
        n = decline_first_name(parts[1], case=case, gender=gender)
        p = decline_patronymic(parts[2], case=case)
        tail = (" " + " ".join(parts[3:])) if len(parts) > 3 else ""
        return f"{s} {n} {p}{tail}"

    if len(parts) == 2:
        gender = detect_gender(parts[0], parts[1])
        s = decline_surname(parts[0], case=case, gender=gender)
        n = decline_first_name(parts[1], case=case, gender=gender)
        return f"{s} {n}"

    if len(parts) == 1:
        return decline_surname(parts[0], case=case)

    return full_name


def inflect_position(position: str, case: str = "gent") -> str:
    if not position or not position.strip():
        return position or ""

    tokens = re.split(r"(\s+|-)", position.strip())
    words_idx = [i for i, t in enumerate(tokens) if t.strip() and t != "-"]
    if not words_idx:
        return position

    out = list(tokens)
    stop = False
    for idx in words_idx:
        if stop:
            break
        w = tokens[idx]
        if len(w) >= 2 and w.isupper():
            continue

        low = w.lower()
        cap = w[0].isupper()
        is_adj = low.endswith(("ый", "ий", "ой", "ая", "яя", "ее", "ое"))
        if is_adj:
            if low.endswith(("ское", "цкое", "гое", "хое")):
                suff = "ого" if case == "gent" else ("ому" if case == "datv" else ("ое" if case == "accs" else ("им" if case == "ablt" else "ом")))
            elif low.endswith("ое"):
                suff = "ого" if case == "gent" else ("ому" if case == "datv" else ("ое" if case == "accs" else ("ым" if case == "ablt" else "ом")))
            elif low.endswith("ее"):
                suff = "его" if case == "gent" else ("ему" if case == "datv" else ("ее" if case == "accs" else ("им" if case == "ablt" else "ем")))
            elif low.endswith("ый"):
                suff = "ого" if case in ("gent", "accs") else ("ому" if case == "datv" else ("ым" if case == "ablt" else "ом"))
            elif low.endswith("ий"):
                prev = low[-3] if len(low) >= 3 else ""
                suff = "его" if (prev in ("ж", "ч", "ш", "щ") and case in ("gent", "accs")) else ("ого" if case in ("gent", "accs") else ("ому" if case == "datv" else ("им" if case == "ablt" else "ом")))
            elif low.endswith("ой"):
                suff = "ого" if case in ("gent", "accs") else ("ому" if case == "datv" else ("ым" if case == "ablt" else "ом"))
            elif low.endswith("ая"):
                suff = "ую" if case == "accs" else "ой"
            else:
                suff = "ого" if case == "gent" else "ому"
            res = low[:-2] + suff
            out[idx] = res.capitalize() if cap else res
            continue

        # Существительное
        if low.endswith("ие"):
            suff = "ия" if case == "gent" else ("ию" if case == "datv" else ("ие" if case == "accs" else ("ием" if case == "ablt" else "ии")))
            res = low[:-2] + suff
        elif low.endswith("ия"):
            suff = "ии" if case in ("gent", "datv", "loct") else ("ию" if case == "accs" else "ией")
            res = low[:-2] + suff
        elif low.endswith("ь"):
            suff = "я" if case in ("gent", "accs") else ("ю" if case == "datv" else ("ем" if case == "ablt" else "е"))
            res = low[:-1] + suff
        elif low.endswith(_VELAR_SH_ENDINGS):
            suff = "и" if case == "gent" else ("е" if case in ("datv", "loct") else ("у" if case == "accs" else "ой"))
            res = low[:-1] + suff
        elif low.endswith("а"):
            suff = "ы" if case == "gent" else ("е" if case in ("datv", "loct") else ("у" if case == "accs" else "ой"))
            res = low[:-1] + suff
        elif low.endswith("я"):
            suff = "и" if case == "gent" else ("е" if case in ("datv", "loct") else ("ю" if case == "accs" else "ей"))
            res = low[:-1] + suff
        else:  # согласный
            suff = "а" if case in ("gent", "accs") else ("у" if case == "datv" else ("ом" if case == "ablt" else "е"))
            res = low + suff

        out[idx] = res.capitalize() if cap else res
        stop = True

    return "".join(out)


def inflect_signatory_full(signatory_text: str, case: str = "gent") -> str:
    if not signatory_text or not signatory_text.strip():
        return ""
    text = signatory_text.strip()
    if ":" in text:
        pos, _, fio = text.partition(":")
        decl_pos = inflect_position(pos.strip(), case)
        decl_fio = inflect_fio(fio.strip(), case)
        return f"{decl_pos}: {decl_fio}" if decl_pos else decl_fio

    parts = text.split()
    if len(parts) >= 4:
        pos_part = " ".join(parts[:-3])
        fio_part = " ".join(parts[-3:])
        return f"{inflect_position(pos_part, case)} {inflect_fio(fio_part, case)}".strip()
    elif len(parts) == 3 and is_patronymic(parts[2]):
        return inflect_fio(text, case)
    elif len(parts) >= 2 and _INITIALS_PATTERN.match(parts[-1]):
        pos_part = " ".join(parts[:-2])
        fio_part = " ".join(parts[-2:])
        decl_p = inflect_position(pos_part, case) if pos_part else ""
        decl_f = inflect_fio(fio_part, case)
        return f"{decl_p} {decl_f}".strip() if decl_p else decl_f

    return inflect_fio(text, case)
