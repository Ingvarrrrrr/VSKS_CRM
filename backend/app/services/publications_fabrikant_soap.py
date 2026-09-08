"""Сборка SOAP-тел для Фабрикант: извещение и addFileToPurchaseNotice (волна резки publications.py)."""
import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException

FABRIKANT_URL = "https://api.fabrikant.ru/multi-integration/common/commercial_trade"

# SOAPAction per operation (tns = binding namespace)
_FABRIKANT_SOAP_ACTION = {
    "zp":               "tns:purchaseNoticeZPCommercial",
    "reduction":        "tns:purchaseNoticeReductionCommercial",
    "price_monitoring": "tns:purchaseNoticePriceMonitoringCommercial",
}
_FABRIKANT_SOAP_ACTION_CHECK     = "tns:checkRequest"
_FABRIKANT_SOAP_ACTION_GET_INFO  = "tns:getProcedureInfo"

NS_PI = "http://api.fabrikant.ru/multi-integration/common/commercial_trade/procedureInfo"

FABRIKANT_CHECK_URL = "https://api.fabrikant.ru/multi-integration/common/commercial_trade/checkRequest"
NS_CR = "http://api.fabrikant.ru/multi-integration/common/commercial_trade/checkRequest"

# ── Фабрикант SOAP: addFileToPurchaseNotice ───────────────────────────────────

NS_UF = "http://api.fabrikant.ru/multi-integration/common/commercial_trade/uploadFile"
NS_T_TYPES = "http://api.fabrikant.ru/multi-integration/common/commercial_trade/types"
FABRIKANT_SOAP_ACTION_ADD_FILE = "tns:addFileToPurchaseNotice"


def _build_add_file_soap_xml(
    purchase_id_str: str,
    file_id: str,
    file_name: str,
    title: str,
    file_bytes_b64: str,
) -> str:
    """Строит SOAP Envelope для операции addFileToPurchaseNotice."""
    def esc(s: str) -> str:
        return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    packet_guid = str(uuid.uuid4())
    create_dt = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+03:00")

    item_guid = str(uuid.uuid4())

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body>"
        f'<uf:addFileToPurchaseNotice xmlns:uf="{NS_UF}" xmlns:t="{NS_T_TYPES}">'
        "<t:header>"
        f"<t:guid>{esc(packet_guid)}</t:guid>"
        f"<t:createDateTime>{create_dt}</t:createDateTime>"
        "</t:header>"
        f"<uf:body><uf:item><t:guid>{esc(item_guid)}</t:guid><uf:addFileToPurchaseNoticeData>"
        f"<uf:purchaseId>{esc(purchase_id_str)}</uf:purchaseId>"
        f"<uf:fileId>{esc(file_id)}</uf:fileId>"
        f"<uf:fileName>{esc(file_name)}</uf:fileName>"
        f"<uf:title>{esc(title)}</uf:title>"
        f"<uf:fileBytes>{file_bytes_b64}</uf:fileBytes>"
        "</uf:addFileToPurchaseNoticeData></uf:item></uf:body>"
        "</uf:addFileToPurchaseNotice>"
        "</soap:Body></soap:Envelope>"
    )



# ── Фабрикант SOAP: извещение ────────────────────────────────────────────────

def _build_soap_xml(payload: dict) -> str:
    """Собирает SOAP-конверт для Фабрикант.

    Тип процедуры задаётся payload["procedure_type"]:
      "zp"              — Запрос предложений (purchaseNoticeZPCommercial)   [default]
      "reduction"       — Редукцион (purchaseNoticeReductionCommercial)
      "price_monitoring"— Мониторинг цен (purchaseNoticePriceMonitoringCommercial)

    Элементы строятся строго по sequence из WSDL. Никаких вымышленных элементов.
    """
    procedure_type = payload.get("procedure_type") or "zp"
    if procedure_type not in ("zp", "reduction", "price_monitoring"):
        raise HTTPException(422, f"Неверный тип процедуры Фабрикант: {procedure_type!r}. Допустимо: zp, reduction, price_monitoring")

    def esc(s):
        return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    purchase_id = esc(payload.get("registry_number") or str(payload.get("purchase_id", "")))
    subject = esc(payload.get("subject") or f"Закупка {purchase_id}")
    nmck = payload.get("nmck", 0)

    now = datetime.now()

    def fdt(d):
        return d.strftime("%Y-%m-%dT%H:%M:%S+03:00")

    def _parse_dt(s):
        try:
            return datetime.fromisoformat(str(s))
        except Exception:
            return None

    if payload.get("proposal_start"):
        start = fdt(_parse_dt(payload["proposal_start"]) or (now + timedelta(hours=1)))
    else:
        start = fdt(now + timedelta(hours=1))

    if payload.get("proposal_end"):
        end_dt = _parse_dt(payload["proposal_end"]) or (now + timedelta(days=7))
    else:
        end_dt = now + timedelta(days=7)
        if payload.get("execution_term"):
            try:
                end_dt = datetime.fromisoformat(str(payload["execution_term"]))
            except Exception:
                pass
    end = fdt(end_dt)

    if payload.get("summing_up_date"):
        summing = fdt(_parse_dt(payload["summing_up_date"]) or (end_dt + timedelta(days=2)))
    else:
        summing = fdt(end_dt + timedelta(days=2))

    NS_PNC = "http://api.fabrikant.ru/multi-integration/common/commercial_trade/purchaseNotice"
    NS_T   = "http://api.fabrikant.ru/multi-integration/common/commercial_trade/types"

    # ── Билдер deliveryPlace (deliveryPlaceType, WSDL): state? → region? → regionOkato? → adress ──
    def _delivery_place_xml(default_addr: str = "") -> str:
        """Порядок элементов строго по sequence WSDL. Каждый опциональный элемент —
        только при наличии значения; adress обязателен (без адреса блок не строим)."""
        addr = payload.get("delivery_address") or default_addr
        if not addr:
            return ""
        xml = "<pnc:deliveryPlace>"
        if payload.get("delivery_state"):
            xml += f"<pnc:state>{esc(payload['delivery_state'])}</pnc:state>"
        if payload.get("delivery_region"):
            xml += f"<pnc:region>{esc(payload['delivery_region'])}</pnc:region>"
        if payload.get("delivery_okato"):
            xml += f"<pnc:regionOkato>{esc(payload['delivery_okato'])}</pnc:regionOkato>"
        xml += f"<pnc:adress>{esc(addr)}</pnc:adress></pnc:deliveryPlace>"
        return xml

    # ── Вспомогательный билдер: initialSumInfo с необязательным pricingMethod перед ним ──
    def _initial_sum_xml(nmck_val: float) -> str:
        """XSD-схема Фабриканта (WSDL проверен 2026-07-28):
        - initialSumInfo — minOccurs=0, элемент необязателен.
        - Если явно запрошено «без НМЦД» (payload["no_nmcd"]) — не слать элемент вовсе.
        - Иначе: есть НМЦД → шлём его; нет НМЦД → откат на сумму позиций;
          нет ни того ни другого → не слать элемент (возвращаем "").
        - pricingMethod=withoutNDSType добавляется перед initialSumInfo
          когда НМЦД отсутствует, но есть сумма позиций.
        """
        if payload.get("no_nmcd"):
            # Пользователь явно потребовал публикацию без НМЦД — элемент не слать
            return ""
        nmck_f = float(nmck_val or 0)
        if nmck_f >= 0.01:
            return (
                f"<pnc:initialSumInfo><pnc:initialSum>{nmck_f:.2f}</pnc:initialSum>"
                f"<pnc:ndsType>without_nds</pnc:ndsType></pnc:initialSumInfo>"
            )
        items_total = sum(
            float(i.get("total_price", 0)) or (float(i.get("unit_price", 0)) * float(i.get("quantity", 1)))
            for i in payload.get("items", [])
            if i.get("item_name")
        )
        items_total = round(items_total, 2)
        if items_total >= 0.01:
            return (
                "<pnc:pricingMethod>withoutNDSType</pnc:pricingMethod>"
                f"<pnc:initialSumInfo><pnc:initialSum>{items_total:.2f}</pnc:initialSum>"
                f"<pnc:ndsType>without_nds</pnc:ndsType></pnc:initialSumInfo>"
            )
        # Neither НМЦД nor item prices — omit the element entirely (minOccurs=0)
        return ""

    # ── Вывод ОКВЭД2 из кода ОКПД2 ──
    def _okved2_from_okpd2(okpd2_code_raw: str) -> str:
        """Возвращает код ОКВЭД2, взяв первые два сегмента ОКПД2. Пример: 29.20.23 → 29.20."""
        parts = okpd2_code_raw.split(".")
        if len(parts) >= 2:
            derived = parts[0] + "." + parts[1]
        else:
            derived = okpd2_code_raw
        return derived

    # ── Билдер lotItems для ЗП (lotItemType) ──
    def _build_lot_items_zp() -> str:
        items_xml = ""
        for idx, item in enumerate(payload.get("items", []), 1):
            if not item.get("item_name"):
                continue
            qty = item.get("quantity", 1)
            up = float(item.get("unit_price", 0))
            tp = float(item.get("total_price", 0)) or (up * qty)
            unit_name = esc(item.get("unit", "шт") or "шт")
            okpd2_code_raw = item.get("okpd2_code") or payload.get("okpd2_code") or ""
            okpd2_code = esc(okpd2_code_raw)
            okpd2_name = esc(item.get("okpd2_name") or item.get("item_name", "Товар")[:100])
            _derived_okved2 = _okved2_from_okpd2(okpd2_code_raw) if okpd2_code_raw else "G"
            okved2_code = esc(item.get("okved2_code") or _derived_okved2)
            okved2_name = esc(item.get("okved2_name") or item.get("okpd2_name") or item.get("item_name", "Товар")[:100])
            # positionPrice(total) before positionPricePerUnit per lotItemType sequence
            # При no_nmcd цены позиций не передаём (minOccurs=0 в lotItemType)
            if up > 0 and not payload.get("no_nmcd"):
                price_xml = (
                    f"<pnc:positionPrice><pnc:price>{tp}</pnc:price><pnc:ndsType>without_nds</pnc:ndsType></pnc:positionPrice>"
                    f"<pnc:positionPricePerUnit><pnc:price>{up}</pnc:price><pnc:ndsType>without_nds</pnc:ndsType></pnc:positionPricePerUnit>"
                )
            else:
                price_xml = ""
            items_xml += (
                f"<pnc:lotItem>"
                f"<pnc:ordinalNumber>{idx}</pnc:ordinalNumber>"
                f"<pnc:positionName>{esc(item['item_name'])}</pnc:positionName>"
                f"<pnc:okpd2><t:code>{okpd2_code}</t:code><t:name>{okpd2_name}</t:name></pnc:okpd2>"
                f"<pnc:okved2><t:code>{okved2_code}</t:code><t:name>{okved2_name}</t:name></pnc:okved2>"
                f"<pnc:okei><t:code>796</t:code><t:name>{unit_name}</t:name></pnc:okei>"
                f"<pnc:qty>{qty}</pnc:qty>"
                f"{price_xml}"
                f"</pnc:lotItem>"
            )
        return f"<pnc:lotItems>{items_xml}</pnc:lotItems>" if items_xml else ""

    # ── Билдер lotItems для Редукциона (lotItemReductionType) ──
    def _build_lot_items_reduction() -> str:
        items_xml = ""
        for idx, item in enumerate(payload.get("items", []), 1):
            if not item.get("item_name"):
                continue
            qty = item.get("quantity", 1)
            unit_name = esc(item.get("unit", "шт") or "шт")
            okpd2_code_raw = item.get("okpd2_code") or payload.get("okpd2_code") or ""
            okpd2_code = esc(okpd2_code_raw)
            okpd2_name = esc(item.get("okpd2_name") or item.get("item_name", "Товар")[:100])
            _derived_okved2 = _okved2_from_okpd2(okpd2_code_raw) if okpd2_code_raw else "G"
            okved2_code = esc(item.get("okved2_code") or _derived_okved2)
            okved2_name = esc(item.get("okved2_name") or item.get("okpd2_name") or item.get("item_name", "Товар")[:100])
            # lotItemReductionType sequence: ordinalNumber? okpd2? okved2? okei? qty? additionalInfo?
            items_xml += (
                f"<pnc:lotItem>"
                f"<pnc:ordinalNumber>{idx}</pnc:ordinalNumber>"
                f"<pnc:okpd2><t:code>{okpd2_code}</t:code><t:name>{okpd2_name}</t:name></pnc:okpd2>"
                f"<pnc:okved2><t:code>{okved2_code}</t:code><t:name>{okved2_name}</t:name></pnc:okved2>"
                f"<pnc:okei><t:code>796</t:code><t:name>{unit_name}</t:name></pnc:okei>"
                f"<pnc:qty>{qty}</pnc:qty>"
                f"</pnc:lotItem>"
            )
        return f"<pnc:lotItems>{items_xml}</pnc:lotItems>" if items_xml else ""

    soap_header = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body>"
    )
    soap_footer = "</soap:Body></soap:Envelope>"

    # ═══════════════════════════════════════════════════════════════════════════
    # ЗП — Запрос предложений (purchaseNoticeZPCommercial)
    # BaseDataType: purchaseId → purchaseCategoryCustom → name → placer? → customer? → notDishonest?
    # lotType sequence: lotId → subject → currency → pricingMethod? → initialSumInfo → deliveryPlace? →
    #   [applicationSupplyNeeded+applicationSupplySumm]? → applicationSupplyExtra? → lotItems →
    #   proposalStartDateTime → proposalEndDateTime → proposalDeterminationDateTime →
    #   summingUpDateTime → lotFramework → lotAllowParticipantsExceedPricesByPositions? → criteria?
    # ═══════════════════════════════════════════════════════════════════════════
    if procedure_type == "zp":
        if payload.get("determination_date"):
            determ = fdt(_parse_dt(payload["determination_date"]) or (end_dt + timedelta(days=1)))
        else:
            determ = fdt(end_dt + timedelta(days=1))

        lot_items = _build_lot_items_zp()
        initial_sum_xml = _initial_sum_xml(nmck)
        delivery_place = _delivery_place_xml(default_addr="Москва")

        body = (
            f'<pnc:purchaseNoticeZPCommercial xmlns:pnc="{NS_PNC}" xmlns:t="{NS_T}">'
            "<pnc:body><pnc:item><pnc:purchaseNoticeZPCommercialData>"
            f"<pnc:purchaseId>{purchase_id}</pnc:purchaseId>"
            "<pnc:purchaseCategoryCustom>Запрос предложений</pnc:purchaseCategoryCustom>"
            f"<pnc:name>{subject}</pnc:name>"
            f"<pnc:placer><t:inn>{esc(payload.get('org_inn') or '')}</t:inn></pnc:placer>"
            f"<pnc:customer><t:inn>{esc(payload.get('org_inn') or '')}</t:inn></pnc:customer>"
            "<pnc:notDishonest>false</pnc:notDishonest>"
            "<pnc:lots><pnc:lot>"
            f"<pnc:lotId>{purchase_id}</pnc:lotId>"
            f"<pnc:subject>{subject}</pnc:subject>"
            "<pnc:currency><t:code>RUB</t:code></pnc:currency>"
            f"{initial_sum_xml}"
            f"{delivery_place}"
            "<pnc:applicationSupplyNeeded>false</pnc:applicationSupplyNeeded>"
            f"{lot_items}"
            f"<pnc:proposalStartDateTime>{start}</pnc:proposalStartDateTime>"
            f"<pnc:proposalEndDateTime>{end}</pnc:proposalEndDateTime>"
            f"<pnc:proposalDeterminationDateTime>{determ}</pnc:proposalDeterminationDateTime>"
            f"<pnc:summingUpDateTime>{summing}</pnc:summingUpDateTime>"
            "<pnc:lotFramework>false</pnc:lotFramework>"
            "</pnc:lot></pnc:lots>"
            "</pnc:purchaseNoticeZPCommercialData></pnc:item></pnc:body>"
            "</pnc:purchaseNoticeZPCommercial>"
        )
        return soap_header + body + soap_footer

    # ═══════════════════════════════════════════════════════════════════════════
    # Редукцион (purchaseNoticeReductionCommercial)
    # BaseDataType: purchaseId → name → placer? → customer? → notDishonest?
    #   (БЕЗ purchaseCategoryCustom!)
    # lotReductionType sequence: lotId → subject → currency → pricingMethod? → initialSumInfo →
    #   deliveryPlace(ОБЯЗАТЕЛЕН!) → [applicationSupplyNeeded+...]? → applicationSupplyExtra? →
    #   lotItems → proposalStartDateTime → proposalEndDateTime → auctionDateStart →
    #   summingUpDateTime → auctionNewBetLimitFrom → auctionNewBetLimitTo →
    #   contractExecutionTerms? → deliveryTerm? → lotPaymentConditions? →
    #   refusalToPurchase? → preferenceInformation? → comment? → lotFramework
    # ═══════════════════════════════════════════════════════════════════════════
    if procedure_type == "reduction":
        missing = []
        if not payload.get("delivery_address"):
            missing.append("место поставки")
        if not payload.get("auction_date_start"):
            missing.append("дата начала редукциона")
        if payload.get("auction_bet_limit_from") is None:
            missing.append("граница ставки от")
        if payload.get("auction_bet_limit_to") is None:
            missing.append("граница ставки до")
        if missing:
            raise HTTPException(422, f"Для редукциона обязательны: {', '.join(missing)}")

        auction_start = fdt(_parse_dt(payload["auction_date_start"]) or (end_dt + timedelta(days=1)))
        bet_from = float(payload["auction_bet_limit_from"])
        bet_to = float(payload["auction_bet_limit_to"])
        delivery_place = _delivery_place_xml()  # delivery_address гарантирован проверкой выше
        lot_items = _build_lot_items_reduction()
        initial_sum_xml = _initial_sum_xml(nmck)

        body = (
            f'<pnc:purchaseNoticeReductionCommercial xmlns:pnc="{NS_PNC}" xmlns:t="{NS_T}">'
            "<pnc:body><pnc:item><pnc:purchaseNoticeReductionCommercialData>"
            f"<pnc:purchaseId>{purchase_id}</pnc:purchaseId>"
            f"<pnc:name>{subject}</pnc:name>"
            f"<pnc:placer><t:inn>{esc(payload.get('org_inn') or '')}</t:inn></pnc:placer>"
            f"<pnc:customer><t:inn>{esc(payload.get('org_inn') or '')}</t:inn></pnc:customer>"
            "<pnc:notDishonest>false</pnc:notDishonest>"
            "<pnc:lots><pnc:lot>"
            f"<pnc:lotId>{purchase_id}</pnc:lotId>"
            f"<pnc:subject>{subject}</pnc:subject>"
            "<pnc:currency><t:code>RUB</t:code></pnc:currency>"
            f"{initial_sum_xml}"
            f"{delivery_place}"
            "<pnc:applicationSupplyNeeded>false</pnc:applicationSupplyNeeded>"
            f"{lot_items}"
            f"<pnc:proposalStartDateTime>{start}</pnc:proposalStartDateTime>"
            f"<pnc:proposalEndDateTime>{end}</pnc:proposalEndDateTime>"
            f"<pnc:auctionDateStart>{auction_start}</pnc:auctionDateStart>"
            f"<pnc:summingUpDateTime>{summing}</pnc:summingUpDateTime>"
            f"<pnc:auctionNewBetLimitFrom>{bet_from:.2f}</pnc:auctionNewBetLimitFrom>"
            f"<pnc:auctionNewBetLimitTo>{bet_to:.2f}</pnc:auctionNewBetLimitTo>"
            "<pnc:lotFramework>false</pnc:lotFramework>"
            "</pnc:lot></pnc:lots>"
            "</pnc:purchaseNoticeReductionCommercialData></pnc:item></pnc:body>"
            "</pnc:purchaseNoticeReductionCommercial>"
        )
        return soap_header + body + soap_footer

    # ═══════════════════════════════════════════════════════════════════════════
    # Мониторинг цен (purchaseNoticePriceMonitoringCommercial)
    # BaseDataType: purchaseId → name → placer? → customer?
    #   (без notDishonest, без purchaseCategoryCustom)
    # PriceMonitoringLotType sequence: lotId → subject → currency →
    #   [okei+qty]?(0..1) → okpd2(1..N, ОБЯЗАТЕЛЕН) → deliveryPlace? →
    #   proposalStartDateTime → proposalEndDateTime
    #   (НЕТ initialSumInfo, НЕТ lotItems, НЕТ цен)
    # ═══════════════════════════════════════════════════════════════════════════
    # procedure_type == "price_monitoring"
    okpd2_code = (payload.get("okpd2_code") or "").strip()
    if not okpd2_code:
        raise HTTPException(422, "Для мониторинга цен обязателен ОКПД2")

    # okei+qty — опционально, берём из первой позиции если есть
    okei_qty_xml = ""
    first_item = next((i for i in payload.get("items", []) if i.get("item_name")), None)
    if first_item:
        qty = first_item.get("quantity", 1)
        unit_name = esc(first_item.get("unit", "шт") or "шт")
        okei_qty_xml = (
            f"<pnc:okei><t:code>796</t:code><t:name>{unit_name}</t:name></pnc:okei>"
            f"<pnc:qty>{qty}</pnc:qty>"
        )

    okpd2_name = esc(payload.get("okpd2_name") or okpd2_code)

    body = (
        f'<pnc:purchaseNoticePriceMonitoringCommercial xmlns:pnc="{NS_PNC}" xmlns:t="{NS_T}">'
        "<pnc:body><pnc:item><pnc:purchaseNoticePriceMonitoringCommercialData>"
        f"<pnc:purchaseId>{purchase_id}</pnc:purchaseId>"
        f"<pnc:name>{subject}</pnc:name>"
        f"<pnc:placer><t:inn>{esc(payload.get('org_inn') or '')}</t:inn></pnc:placer>"
        f"<pnc:customer><t:inn>{esc(payload.get('org_inn') or '')}</t:inn></pnc:customer>"
        "<pnc:lots><pnc:lot>"
        f"<pnc:lotId>{purchase_id}</pnc:lotId>"
        f"<pnc:subject>{subject}</pnc:subject>"
        "<pnc:currency><t:code>RUB</t:code></pnc:currency>"
        f"{okei_qty_xml}"
        f"<pnc:okpd2><t:code>{esc(okpd2_code)}</t:code><t:name>{okpd2_name}</t:name></pnc:okpd2>"
        # deliveryPlace опционален (minOccurs=0) — добавляем только при наличии адреса
        f"{_delivery_place_xml()}"
        f"<pnc:proposalStartDateTime>{start}</pnc:proposalStartDateTime>"
        f"<pnc:proposalEndDateTime>{end}</pnc:proposalEndDateTime>"
        "</pnc:lot></pnc:lots>"
        "</pnc:purchaseNoticePriceMonitoringCommercialData></pnc:item></pnc:body>"
        "</pnc:purchaseNoticePriceMonitoringCommercial>"
    )
    return soap_header + body + soap_footer
