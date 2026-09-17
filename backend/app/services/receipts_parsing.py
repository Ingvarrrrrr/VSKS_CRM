"""Pure parsing/extraction logic for fiscal receipts (no DB, no HTTP).

Split out of app/routers/purchase_receipts.py (Правило №5, сессия 2026-09-08):
this module holds the FNS-JSON / QR-string / proverkacheka-HTML parsers and
the item-matching heuristic shared by receipt creation (receipts_creation.py),
recompute (receipts_recompute.py) and rendering (receipts_render.py).

Historical import path app.routers.purchase_receipts re-exports every public
name here — external callers (contractors.py, diag.py, purchases.py,
backfills.py, purchase_items_import.py) keep working unchanged.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.utils.numbers import to_decimal


def _kop_to_rub(v):
    """Convert копейки → рубли. Accepts None / int / float / str."""
    if v is None:
        return None
    try:
        return (Decimal(str(v)) / Decimal('100')).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except Exception:
            return None
    return None


def _parse_fns_json_receipt(raw: dict) -> dict:
    """Map a single FNS-mobile-app JSON entry → dict with internal field names."""
    r = (
        (raw.get('ticket') or {}).get('document', {}).get('receipt')
        or raw.get('receipt')
        or raw
    ) or {}

    items = []
    for it in (r.get('items') or []):
        try:
            qty = Decimal(str(it.get('quantity') or 1))
        except Exception:
            qty = Decimal('1')
        items.append({
            'name': (it.get('name') or '').strip(),
            'quantity': qty,
            'price': _kop_to_rub(it.get('price')),
            'sum': _kop_to_rub(it.get('sum')),
            'nds': it.get('nds'),
            # Phase 26-fff: map ФФД nds-code → vat_rate string at parse time so
            # _create_receipt_with_items / _recompute_from_receipts_core can
            # write it into PurchaseItem.vat_rate. Без этого vat_rate всегда
            # был None для JSON-импорта (только HTML-парсер ставил vat_rate).
            'vat_rate': _nds_code_to_rate_str(it.get('nds')),
        })

    fd_num = r.get('fiscalDocumentNumber')
    if isinstance(fd_num, str) and fd_num.isdigit():
        fd_num = int(fd_num)
    elif not isinstance(fd_num, int):
        fd_num = None

    return {
        'fiscal_drive_number': (str(r.get('fiscalDriveNumber') or '').strip() or None),
        'fiscal_document_number': fd_num,
        'fiscal_sign': (str(r.get('fiscalSign') or '').strip() or None),
        'kkt_reg_id': (str(r.get('kktRegId') or '').strip() or None),
        'receipt_datetime': _parse_dt(r.get('dateTime')),
        'total_sum': _kop_to_rub(r.get('totalSum')),
        'cash_sum': _kop_to_rub(r.get('cashTotalSum')),
        'ecash_sum': _kop_to_rub(r.get('ecashTotalSum')),
        'prepaid_sum': _kop_to_rub(r.get('prepaidSum')),
        'nds_sum': _kop_to_rub(r.get('ndsSum')),
        'seller_name': ((r.get('user') or '').strip() or None),
        'seller_inn': (str(r.get('userInn') or '').strip() or None),
        'retail_place': r.get('retailPlace'),
        'retail_place_address': r.get('retailPlaceAddress'),
        'operator': r.get('operator'),
        'operator_inn': (str(r.get('operatorInn') or '').strip() or None),
        'taxation_type': r.get('appliedTaxationType') or r.get('taxationType'),
        'items': items,
    }


def _parse_qr_string(qr: str) -> dict:
    """Parse QR string `t=...&s=...&fn=...&i=...&fp=...&n=...` → dict."""
    parts = {}
    for chunk in (qr or '').strip().split('&'):
        if '=' in chunk:
            k, v = chunk.split('=', 1)
            parts[k.strip()] = v.strip()

    dt = None
    if 't' in parts:
        s = parts['t']
        for fmt in ('%Y%m%dT%H%M%S', '%Y%m%dT%H%M'):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except Exception:
                continue

    total = None
    if 's' in parts:
        try:
            total = Decimal(parts['s'])
        except Exception:
            total = None

    fd_num = None
    if parts.get('i', '').isdigit():
        fd_num = int(parts['i'])

    return {
        'fiscal_drive_number': parts.get('fn') or None,
        'fiscal_document_number': fd_num,
        'fiscal_sign': parts.get('fp') or None,
        'receipt_datetime': dt,
        'total_sum': total,
    }


def _items_match_score(item_a, item_b) -> int:
    """
    Phase 26-BB: возвращает количество совпавших полей (0-4) для сопоставления
    позиции из БД (item_a — ORM объект) и позиции из raw_json чека (item_b — dict).
    Поля: name (similarity >= 0.7), quantity, unit_price, total_price.
    item_b['price'] и item_b['sum'] — уже в рублях (прошли через _extract_items или _parse_fns_json_receipt).
    """
    import difflib
    score = 0
    # name
    name_a = (getattr(item_a, 'item_name', None) or '').strip().lower()
    name_b = str(item_b.get('name') or '').strip().lower()
    if name_a and name_b:
        sim = difflib.SequenceMatcher(None, name_a, name_b).ratio()
        if sim >= 0.7:
            score += 1
    # quantity
    try:
        qa = Decimal(str(item_a.quantity or 0))
        qb = Decimal(str(item_b.get('quantity') or item_b.get('qty') or 0))
        if qa > 0 and qb > 0:
            ratio = abs(qa - qb) / max(qa, qb)
            if ratio <= Decimal('0.01'):
                score += 1
    except Exception:
        pass
    # unit_price
    try:
        pa = Decimal(str(item_a.unit_price or 0))
        pb = Decimal(str(item_b.get('price') or 0))
        if abs(pa - pb) <= Decimal('0.01'):
            score += 1
    except Exception:
        pass
    # total_price
    try:
        ta = Decimal(str(item_a.total_price or 0))
        tb_raw = item_b.get('sum') or item_b.get('total')
        tb = Decimal(str(tb_raw or 0))
        if abs(ta - tb) <= Decimal('0.01'):
            score += 1
    except Exception:
        pass
    return score


# ФФД 1.2 тег 1199 «Ставка НДС» → строка ставки для PurchaseItem.vat_rate.
# None — без НДС (код 6) или неизвестный код: ставка не определена.
NDS_CODE_TO_RATE_STR = {
    1: "20%",
    2: "10%",
    3: "20/120",
    4: "10/110",
    5: "0%",
    7: "5%",
    8: "7%",
    9: "5/105",
    10: "7/107",
    11: "22%",
    12: "22/122",
}


def _nds_code_to_rate_str(code) -> str | None:
    """Маппит код ФФД 'nds' (тег 1199) в строку ставки ('22%', '5%', ...).
    None для 'без НДС' (код 6) и неизвестных кодов."""
    try:
        return NDS_CODE_TO_RATE_STR.get(int(code))
    except (TypeError, ValueError):
        return None


def _get_raw_receipt(r) -> dict:
    """Pull the FNS receipt sub-dict regardless of payload shape variant."""
    raw = r.raw_json or {}
    if not isinstance(raw, dict):
        return {}
    if 'ticket' in raw and isinstance(raw['ticket'], dict):
        return raw.get('ticket', {}).get('document', {}).get('receipt', {}) or {}
    if 'receipt' in raw and isinstance(raw['receipt'], dict):
        return raw['receipt']
    return raw


def _build_qr_string(r) -> str:
    """Compose the canonical ФНС QR string `t=...&s=...&fn=...&i=...&fp=...&n=...`."""
    parts = []
    if r.receipt_datetime:
        try:
            parts.append(f"t={r.receipt_datetime.strftime('%Y%m%dT%H%M')}")
        except Exception:
            pass
    if r.total_sum is not None:
        try:
            parts.append(f"s={float(r.total_sum):.2f}")
        except Exception:
            pass
    if r.fiscal_drive_number:
        parts.append(f"fn={r.fiscal_drive_number}")
    if r.fiscal_document_number:
        parts.append(f"i={r.fiscal_document_number}")
    if r.fiscal_sign:
        parts.append(f"fp={r.fiscal_sign}")
    raw = _get_raw_receipt(r)
    op = raw.get('operationType') or 1
    parts.append(f"n={op}")
    return '&'.join(parts)


def _extract_items_from_proverkacheka_html(html: str) -> list:
    """Phase 26-EE/MM: парсер HTML-таблицы товаров от proverkacheka.com.
    Парсит и НДС-строки (b-check_vblock-last с 'НДС со ставкой X%').
    """
    if not html or not isinstance(html, str):
        return []
    import re as _re

    def _clean(s):
        s = _re.sub(r'<[^>]+>', '', s)
        s = s.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        return s.strip()

    out = []
    current_item = None
    # Все строки с классом b-check_item (товары + НДС)
    all_rows = _re.findall(
        r'<tr[^>]*class="([^"]*b-check_item[^"]*)"[^>]*>(.*?)</tr>',
        html,
        flags=_re.DOTALL,
    )
    for class_attr, row in all_rows:
        cells = _re.findall(r'<td[^>]*>(.*?)</td>', row, flags=_re.DOTALL)
        cleaned = [_clean(c) for c in cells]
        is_first = 'b-check_vblock-first' in class_attr
        is_last = 'b-check_vblock-last' in class_attr
        if is_first and len(cleaned) >= 5:
            # Новая позиция: cells [№, name, price, qty, sum]
            try:
                name = cleaned[1]
                # Единый разборщик чисел (Правило №6, app/utils/numbers.py) —
                # replace(',', '.') "в лоб" ломает точку-разделитель тысяч
                # (см. дефект позиции закупки id=3166, 2026-09-14).
                price = float(to_decimal(cleaned[2]) or 0)
                qty = float(to_decimal(cleaned[3]) or 1)
                sm = float(to_decimal(cleaned[4]) or 0)
                if not name:
                    current_item = None
                    continue
                current_item = {
                    'name': name,
                    'quantity': qty,
                    'qty': qty,
                    'price': price,
                    'sum': sm,
                    'vat_rate': None,
                }
                out.append(current_item)
            except Exception:
                current_item = None
                continue
        elif is_last and current_item is not None:
            # НДС-строка позиции: ищем "НДС со ставкой X%"
            for c in cleaned:
                m = _re.search(r'НДС\s*со\s*ставкой\s*(\d+(?:[.,]\d+)?)\s*%', c)
                if m:
                    rate = m.group(1).replace(',', '.')
                    current_item['vat_rate'] = f"{rate}%"
                    break
            current_item = None  # next first opens new item
    return out


def _parse_proverkacheka_html_receipt(html: str) -> dict:
    """Извлечь чек целиком (шапка + позиции) из сохранённой HTML-страницы
    proverkacheka.com — используется загрузкой .html/.htm файла (когда QR
    отсканировать нельзя и JSON-экспорта нет, только HTML-страница «Проверки
    чека» сохранённая из браузера).

    Товары — через уже существующий _extract_items_from_proverkacheka_html
    (тот же парсер, что fallback-путь для /from-qr-fetch и _extract_items,
    ПРАВИЛО №6 — не второй парсер таблицы позиций, а переиспользование).

    Шапка (ИНН/ФН/ФД/ФП/дата/итог) на proverkacheka.com не имеет отдельного
    предсказуемого класса как таблица товаров — извлекается best-effort
    регулярками по тексту без тегов. Отсутствие ФН/ФД/ФП не блокирует импорт:
    идемпотентность и дедуп в receipts_creation.py в этом случае откатываются
    на мягкую проверку (seller_inn+receipt_datetime+total_sum) либо не
    срабатывают вовсе — осознанная деградация, не баг. Признак «чек разобран»
    для вызывающего кода — непустой items (см. purchase_receipts_import.py).
    """
    if not html or not isinstance(html, str):
        return {'items': []}
    import re as _re

    items = _extract_items_from_proverkacheka_html(html)

    text = _re.sub(r'<[^>]+>', ' ', html)
    text = (
        text.replace('&nbsp;', ' ')
        .replace('&amp;', '&')
        .replace('&lt;', '<')
        .replace('&gt;', '>')
    )
    text = _re.sub(r'\s+', ' ', text)

    def _search(pattern):
        return _re.search(pattern, text, flags=_re.IGNORECASE)

    seller_inn = None
    m = _search(r'ИНН[:\s№]*([0-9]{10,12})')
    if m:
        seller_inn = m.group(1)

    fiscal_drive_number = None
    m = _search(r'\bФН[:\s№]*([0-9]{10,20})')
    if m:
        fiscal_drive_number = m.group(1)

    fiscal_document_number = None
    m = _search(r'\bФД[:\s№]*([0-9]{1,10})\b')
    if m:
        try:
            fiscal_document_number = int(m.group(1))
        except ValueError:
            fiscal_document_number = None

    fiscal_sign = None
    m = _search(r'\bФП[Д]?[:\s№]*([0-9]{6,15})')
    if m:
        fiscal_sign = m.group(1)

    total_sum = None
    m = _search(r'ИТОГ[О]?[:\s]*([0-9][0-9\s.,]*[0-9])')
    if m:
        total_sum = to_decimal(m.group(1))

    receipt_datetime = None
    m = _search(r'(\d{2}\.\d{2}\.\d{4})\D{1,6}(\d{2}:\d{2})')
    if m:
        try:
            receipt_datetime = datetime.strptime(f"{m.group(1)} {m.group(2)}", '%d.%m.%Y %H:%M')
        except Exception:
            receipt_datetime = None

    return {
        'fiscal_drive_number': fiscal_drive_number,
        'fiscal_document_number': fiscal_document_number,
        'fiscal_sign': fiscal_sign,
        'receipt_datetime': receipt_datetime,
        'total_sum': total_sum,
        'seller_name': None,
        'seller_inn': seller_inn,
        'items': items,
    }


def _extract_items(raw) -> list:
    """Pull items out of the raw_json regardless of FNS shape variant."""
    if not isinstance(raw, dict):
        return []
    items_src = None
    ticket = raw.get('ticket')
    if isinstance(ticket, dict):
        doc = ticket.get('document')
        if isinstance(doc, dict):
            rcpt = doc.get('receipt')
            if isinstance(rcpt, dict):
                items_src = rcpt.get('items')
    if items_src is None:
        rcpt = raw.get('receipt')
        if isinstance(rcpt, dict):
            items_src = rcpt.get('items')
    if items_src is None:
        items_src = raw.get('items')
    if isinstance(items_src, list) and items_src:
        out = []
        for it in items_src:
            if not isinstance(it, dict):
                continue
            try:
                qty = float(it.get('quantity') or 1)
            except Exception:
                qty = 1.0
            try:
                price = float(it.get('price') or 0) / 100.0
            except Exception:
                price = 0.0
            try:
                sm = float(it.get('sum') or 0) / 100.0
            except Exception:
                sm = 0.0
            out.append({
                'name': str(it.get('name') or '').strip(),
                'quantity': qty,
                'qty': qty,
                'price': price,
                'sum': sm,
                'nds': it.get('nds'),
                'vat_rate': _nds_code_to_rate_str(it.get('nds')),
            })
        if out:
            return out
    # Phase 26-EE fallback: proverkacheka.com (JSON приоритетнее HTML — содержит
    # точные nds-коды; HTML парсер не извлекает nds=11 для ставки 22% т.к. в
    # рендере proverkacheka нет строки "НДС со ставкой 22%")
    pv = raw.get('proverkacheka')
    if isinstance(pv, dict):
        data = pv.get('data')
        if isinstance(data, dict):
            # Phase 26-ggg: JSON путь приоритет
            pvj = data.get('json')
            if isinstance(pvj, dict):
                json_items = pvj.get('items')
                if isinstance(json_items, list) and json_items:
                    return _extract_items({'items': json_items})
            html = data.get('html')
            if html:
                return _extract_items_from_proverkacheka_html(html)
    return []


def _items_for_render(r) -> list:
    """Items normalized to rubles for renderer use.

    raw_json items могут быть либо в копейках (original FFD JSON path)
    либо уже в рублях (proverkacheka.com fallback через _extract_items).
    Этот helper делает единый source of truth для рендеров.
    """
    raw = _get_raw_receipt(r)
    raw_items = raw.get('items') if isinstance(raw, dict) else None
    if isinstance(raw_items, list) and raw_items:
        # Original FFD shape — price/sum в копейках
        out = []
        for it in raw_items:
            if not isinstance(it, dict):
                continue
            try:
                price_rub = float(it.get('price') or 0) / 100.0
            except Exception:
                price_rub = 0.0
            try:
                sum_rub = float(it.get('sum') or 0) / 100.0
            except Exception:
                sum_rub = 0.0
            # ndsSum тоже из копеек FFD
            nds_sum_kop = it.get('ndsSum')
            try:
                nds_sum_rub = float(nds_sum_kop) / 100.0 if nds_sum_kop is not None else None
            except Exception:
                nds_sum_rub = None
            out.append({**it, 'price_rub': price_rub, 'sum_rub': sum_rub, 'nds_sum_rub': nds_sum_rub})
        return out
    # Fallback path — _extract_items already returns price/sum в рублях
    items = _extract_items(r.raw_json or {})
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            price_rub = float(it.get('price') or 0)
        except Exception:
            price_rub = 0.0
        try:
            sum_rub = float(it.get('sum') or 0)
        except Exception:
            sum_rub = 0.0
        out.append({**it, 'price_rub': price_rub, 'sum_rub': sum_rub, 'nds_sum_rub': None})
    return out


# ── proverkacheka.com error classification (Правило №6, 2026-09-17) ─────────
# Владелец (жалоба п.6а): «Сервис получения чеков временно недоступен, чек
# будет запрашиваться в течение 24ч — это ответ приложения налоговой, а не
# наш лимит. У нас пишет что какой-то лимит не прошёл». Причина: старая
# проверка `"уже" in msg_str.lower()` слишком широкая — сообщение ФНС о том,
# что чек ЕЩЁ ОБРАБАТЫВАЕТСЯ («чек уже находится в обработке», «данные ещё не
# поступили» и т.п.) содержит слово «уже» и ошибочно попадало в ветку
# FNS_RATE_LIMIT, показывая пользователю текст про лимит запросов вместо
# честного «подождите/введите вручную сейчас».
#
# Единственное место, где proverkacheka-ответ превращается в текст для
# пользователя — эта функция. Оба вызывающих (purchase_receipts_import.py
# ::import_receipt_qr_fetch и purchase_items_import_smart.py — умный импорт
# по QR из фото) обязаны использовать её, а не заводить свою классификацию
# (ПРАВИЛО №6).
def classify_proverkacheka_error(msg_str: str) -> dict:
    """Разобрать текст ошибки proverkacheka.com/ФНС в понятный код+сообщение.

    Возвращает {"status": int, "code": str, "message": str, "hint": str|None}.
    status — HTTP-код, с которым нужно поднять HTTPException(status, detail={...}).

    Три варианта:
      RECEIPT_PENDING   (409) — чек существует, но ФНС ещё не отдала данные
                          (обработка может занимать до суток). Честно говорим
                          что делать: приложить чек и ввести данные вручную
                          сейчас, либо вернуться позже.
      FNS_RATE_LIMIT     (429) — proverkacheka.com реально ограничил ЧАСТОТУ
                          обращений с этого токена (узкое совпадение, без
                          слова «уже», которое ложно матчило RECEIPT_PENDING).
      RECEIPT_NOT_FOUND  (400) — чек не найден в ФНС вовсе (неверный QR и т.п.).
    """
    msg = (msg_str or "").strip()
    low = msg.lower()

    # Узкое совпадение реального троттлинга: «превышено количество запросов/
    # обращений» — НЕ просто слово «превышено» само по себе (оно может
    # встретиться и в фразах про обработку).
    is_rate_limit = (
        ("превышен" in low or "превышено" in low)
        and ("запрос" in low or "обращен" in low or "лимит" in low)
    )
    if is_rate_limit:
        return {
            "status": 429,
            "code": "FNS_RATE_LIMIT",
            "message": "proverkacheka.com временно ограничил частоту запросов с этого токена. Попробуйте через 1–2 минуты — либо приложите фото/PDF чека и введите данные вручную сейчас.",
            "hint": msg or None,
        }

    # Чек существует, но ФНС ещё не отдала по нему данные — обработка «в
    # очереди» может занимать до суток. Ключевые слова взяты из реальных
    # формулировок ФНС/proverkacheka про недоступность/обработку/срок.
    pending_markers = (
        "недоступен", "недоступн", "обраб", "ожида", "поступ", "24 час",
        "24ч", "сутки", "суток", "будет доступ", "не готов", "в очеред",
        "повтор", "уже",
    )
    if any(m in low for m in pending_markers):
        return {
            "status": 409,
            "code": "RECEIPT_PENDING",
            "message": (
                "ФНС ещё не вернула данные по этому чеку — обработка может занимать "
                "до 24 часов. Приложите фото/PDF чека и введите данные вручную сейчас, "
                "либо вернитесь к загрузке позже."
            ),
            "hint": msg or None,
        }

    if msg:
        return {
            "status": 400,
            "code": "RECEIPT_NOT_FOUND",
            "message": f"Чек не найден в ФНС: {msg}",
            "hint": msg,
        }
    return {
        "status": 400,
        "code": "RECEIPT_NOT_FOUND",
        "message": "Чек не найден в ФНС (proverkacheka.com)",
        "hint": None,
    }
