"""Снимок карточки товара каталога (фото + актуальность цены) — единственный
источник (Правило №6, владелец 2026-09-20) для мест, которым нужны эти поля
у товара, но которые НЕ являются GET /api/products/ (список/карточка каталога
сами строят price_freshness через app.services.price_freshness напрямую и
получают has_photo через ProductOut._compute_has_photo, см.
app/schemas/products.py — тот же приём photo_size вместо photo_data, здесь не
дублируется, а переиспользуется формула, просто оформленная функцией для
потребителей ВНЕ ProductOut).

resolve_photo_url() — формула фолбэка «внешняя ссылка, иначе эндпоинт bytea,
иначе ничего», раньше буквально продублированная в
app.routers.products_match._score_product_candidates и
app.services.plan_to_wish._candidate_from_type_row — обе переведены на эту
функцию тем же коммитом, третья копия (app.services.wish_serializers) больше
не заводится.
"""
from typing import Optional

from app.services.price_freshness import FreshnessContext, evaluate as evaluate_freshness


def resolve_photo_url(photo_url: Optional[str], has_bytea_photo: bool, product_id: int) -> Optional[str]:
    """photo_url колонки, если задана (внешняя ссылка — маркетплейс и т.п.);
    иначе, если фото закэшировано в БД (photo_data/photo_size), путь к
    GET /api/products/{id}/photo; иначе None (используем photo_link на фронте,
    если он есть — это уже забота вызывающей стороны)."""
    return photo_url or (f"/api/products/{product_id}/photo" if has_bytea_photo else None)


def build_product_snapshot(product, freshness_ctx: FreshnessContext) -> dict:
    """has_photo/photo_url/photo_link/description/description_44fz/
    price_updated_at/price_source/price_source_ref/price_freshness для одного
    Product (ORM-инстанс). description/description_44fz добавлены (владелец,
    2026-09-20): ТЗ заявки (WishTzSection.vue на фронте) раньше брало их из
    полного каталога — без них снимок позиции заявки не может показать ТЗ.

    Безопасно вызывать, когда Product.photo_data был deferred (список/выборка
    без .options(defer(Product.photo_data)) — не читаем): has_photo/photo_url
    построены из product.photo_size (дешёвый int, всегда выбирается), не из
    самих байт — тот же приём, что и ProductOut._compute_has_photo и
    products_match._score_product_candidates (has_bytea_photo)."""
    has_bytea_photo = getattr(product, "photo_size", None) is not None
    return {
        "product_id": product.id,
        "has_photo": has_bytea_photo,
        "photo_url": resolve_photo_url(product.photo_url, has_bytea_photo, product.id),
        "photo_link": product.photo_link,
        "description": product.description,
        "description_44fz": product.description_44fz,
        "price_updated_at": product.price_updated_at,
        "price_source": product.price_source,
        "price_source_ref": product.price_source_ref,
        "price_freshness": evaluate_freshness(product, freshness_ctx),
    }
