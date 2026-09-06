-- audit_purchase_amounts.sql — read-only сверка формулы "effective_amount"
-- (см. app/services/purchase_amounts.py::purchase_amounts, вторая волна
-- решения владельца 2026-09-05 — по стадии статуса, с длинной цепочкой
-- фолбэков:
--   paid      -> payment_amount -> payment_amount_declared ->
--                acceptance_doc_amount -> contract_price ->
--                Σ contract_items.total -> planned_total_price ->
--                Σ purchase_items.total_price
--   delivered -> acceptance_doc_amount -> contract_price ->
--                Σ contract_items.total -> planned_total_price ->
--                Σ purchase_items.total_price
--   work_in_progress/contracted/ordered -> contract_price ->
--                Σ contract_items.total -> planned_total_price ->
--                Σ purchase_items.total_price
--   до договора -> planned_total_price -> Σ purchase_items.total_price
--   рамочная голова с Contract.max_amount — поверх всего)
-- против 9 существующих backend-формул "суммы закупки" (те же 9,
-- что и в app/services/purchase_amounts_audit.py — там же точные file:line
-- ссылки на источник и Python-эквивалент каждой). ТОЛЬКО SELECT, ничего не
-- пишет — безопасно на проде read-only.
--
-- Запуск (одним stdin-файлом, без интерактивного psql):
--   docker exec -i vsks_crm-db-1 psql -U vsks -d vsks_crm -f - < backend/scripts/audit_purchase_amounts.sql
-- (на проде — тот же контейнер БД под его именем, соединение только внутри
-- docker-сети, см. ПРАВИЛО №4 в CLAUDE.md).
--
-- Формула 8 (feo_plan.purchase_item_fact_amount) агрегируется до уровня
-- закупки (Σ по её позициям, та же пропорция ratio, что и в оригинале) —
-- см. item_fact/item_fact_calc/purchase_fact ниже.

WITH contract_item_totals AS (
    SELECT purchase_id, COALESCE(SUM(total), 0) AS ci_total
    FROM contract_items
    GROUP BY purchase_id
),
purchase_item_totals AS (
    SELECT purchase_id, COALESCE(SUM(total_price), 0) AS pi_total, COUNT(*) AS items_count
    FROM purchase_items
    GROUP BY purchase_id
),
contract_item_by_source AS (
    SELECT source_item_id, COALESCE(SUM(total), 0) AS ci_total
    FROM contract_items
    WHERE source_item_id IS NOT NULL
    GROUP BY source_item_id
),
contract_purchase_sum AS (
    SELECT contract_id, COALESCE(SUM(COALESCE(contract_price, planned_total_price, total_nmck, 0)), 0) AS csum
    FROM purchases
    WHERE contract_id IS NOT NULL
    GROUP BY contract_id
),
base AS (
    SELECT
        p.*,
        cit.ci_total,
        pit.pi_total,
        (p.purchase_contract_type IN ('framework_cumulative', 'framework_with_amount')
            AND p.parent_purchase_id IS NULL) AS is_framework_head
    FROM purchases p
    LEFT JOIN contract_item_totals cit ON cit.purchase_id = p.id
    LEFT JOIN purchase_item_totals pit ON pit.purchase_id = p.id
),
effective AS (
    -- Единственный источник истины этой сверки — та же формула, что и
    -- purchase_amounts.purchase_amounts()/load_purchase_amounts() (полная
    -- цепочка, включая item-фолбэки на contract_items/purchase_items).
    -- ПРАВИЛО №6 (2026-09-06): effective_amount_expr() (SQL-выражение для
    -- чужих агрегатов — dashboard.py/subsidies.py/feo_categories.py) теперь
    -- ТОЖЕ учитывает рамочную голову (Contract.max_amount) — та же формула,
    -- что и здесь, для этой ветки; единственное оставшееся расхождение
    -- между effective_amount_expr() и этой read-only сверкой — item-фолбэки
    -- (Σ contract_items/Σ purchase_items), которым в чужом агрегате
    -- неоткуда взяться без JOIN (см. докстринг effective_amount_expr()).
    SELECT
        b.*,
        c.max_amount AS framework_max_amount,
        CASE
            WHEN b.is_framework_head AND b.contract_id IS NOT NULL AND c.max_amount IS NOT NULL
                THEN c.max_amount
            WHEN b.status = 'paid' THEN COALESCE(
                b.payment_amount, b.payment_amount_declared, b.acceptance_doc_amount,
                b.contract_price, b.ci_total, b.planned_total_price, b.pi_total
            )
            WHEN b.status = 'delivered' THEN COALESCE(
                b.acceptance_doc_amount, b.contract_price, b.ci_total,
                b.planned_total_price, b.pi_total
            )
            WHEN b.status IN ('work_in_progress', 'contracted', 'ordered')
                THEN COALESCE(b.contract_price, b.ci_total, b.planned_total_price, b.pi_total)
            ELSE COALESCE(b.planned_total_price, b.pi_total)
        END AS effective_amount
    FROM base b
    LEFT JOIN contracts c ON c.id = b.contract_id
),
item_fact AS (
    SELECT
        pi.purchase_id,
        pi.total_price,
        pit.pi_total,
        pit.items_count,
        p.status,
        p.contract_price,
        p.acceptance_doc_amount,
        pi.final_total,
        cis.ci_total AS contract_item_total
    FROM purchase_items pi
    JOIN purchases p ON p.id = pi.purchase_id
    LEFT JOIN contract_item_by_source cis ON cis.source_item_id = pi.id
    LEFT JOIN purchase_item_totals pit ON pit.purchase_id = pi.purchase_id
),
item_fact_calc AS (
    SELECT
        purchase_id,
        CASE
            WHEN status IN ('work_in_progress', 'contracted', 'ordered') THEN
                CASE
                    WHEN contract_item_total IS NOT NULL THEN contract_item_total
                    WHEN final_total IS NOT NULL THEN final_total
                    WHEN contract_price IS NOT NULL THEN
                        CASE
                            WHEN items_count = 1 THEN contract_price
                            WHEN pi_total > 0 THEN ROUND(contract_price * (total_price / pi_total), 2)
                            ELSE ROUND(contract_price / items_count, 2)
                        END
                    ELSE NULL
                END
            WHEN status IN ('delivered', 'paid') THEN
                CASE
                    WHEN contract_item_total IS NOT NULL THEN contract_item_total
                    WHEN final_total IS NOT NULL THEN final_total
                    WHEN acceptance_doc_amount IS NOT NULL THEN
                        CASE
                            WHEN items_count = 1 THEN acceptance_doc_amount
                            WHEN pi_total > 0 THEN ROUND(acceptance_doc_amount * (total_price / pi_total), 2)
                            ELSE ROUND(acceptance_doc_amount / items_count, 2)
                        END
                    ELSE COALESCE(total_price, 0)
                END
            ELSE NULL
        END AS item_fact
    FROM item_fact
),
purchase_fact AS (
    SELECT purchase_id, SUM(item_fact) AS fact_total, COUNT(item_fact) AS n_nonnull
    FROM item_fact_calc
    GROUP BY purchase_id
),
formulas AS (
    SELECT
        e.id,
        e.status,
        e.effective_amount,
        COALESCE(e.contract_price, e.planned_total_price) AS f2a,
        COALESCE(e.payment_amount, e.contract_price, e.planned_total_price) AS f2b,
        COALESCE(NULLIF(e.nmck, 0), NULLIF(e.planned_total_price, 0), 0) AS f3,
        COALESCE(NULLIF(e.contract_price, 0), e.ci_total, 0) AS f4a,
        COALESCE(
            NULLIF(e.contract_price, 0), NULLIF(e.total_nmck, 0), NULLIF(e.nmck, 0),
            NULLIF(e.planned_total_price, 0), e.pi_total, 0
        ) AS f4b,
        CASE
            WHEN e.contract_id IS NOT NULL
                 AND e.purchase_contract_type IN ('framework_cumulative', 'framework_with_amount')
            THEN COALESCE(e.framework_max_amount, cps.csum, 0)
            ELSE NULL
        END AS f5,
        (e.contract_id IS NOT NULL
            AND e.purchase_contract_type IN ('framework_cumulative', 'framework_with_amount')) AS f5_applicable,
        COALESCE(NULLIF(e.contract_price, 0), NULLIF(e.planned_total_price, 0), 0) AS f6,
        CASE
            WHEN e.status IN ('delivered', 'paid') AND e.feo_category_id IS NOT NULL
            THEN COALESCE(e.final_total_amount, e.planned_total_price)
            ELSE NULL
        END AS f7,
        (e.status IN ('delivered', 'paid') AND e.feo_category_id IS NOT NULL) AS f7_applicable,
        pf.fact_total AS f8,
        (COALESCE(pf.n_nonnull, 0) > 0) AS f8_applicable,
        CASE WHEN e.status = 'cancelled' THEN NULL ELSE COALESCE(e.planned_total_price, 0) END AS f9,
        (e.status <> 'cancelled') AS f9_applicable
    FROM effective e
    LEFT JOIN contract_purchase_sum cps ON cps.contract_id = e.contract_id
    LEFT JOIN purchase_fact pf ON pf.purchase_id = e.id
)
SELECT 'M_total (все закупки)' AS formula, COUNT(*) AS applicable, NULL::bigint AS divergent FROM formulas
UNION ALL
SELECT '2a_dashboard_contract_or_planned', COUNT(*),
       COUNT(*) FILTER (WHERE f2a IS DISTINCT FROM effective_amount) FROM formulas
UNION ALL
SELECT '2b_dashboard_payment_or_contract_or_planned', COUNT(*),
       COUNT(*) FILTER (WHERE f2b IS DISTINCT FROM effective_amount) FROM formulas
UNION ALL
SELECT '3_purchase_export_nmck', COUNT(*),
       COUNT(*) FILTER (WHERE f3 IS DISTINCT FROM effective_amount) FROM formulas
UNION ALL
SELECT '4a_documents_contract_family', COUNT(*),
       COUNT(*) FILTER (WHERE f4a IS DISTINCT FROM effective_amount) FROM formulas
UNION ALL
SELECT '4b_documents_other', COUNT(*),
       COUNT(*) FILTER (WHERE f4b IS DISTINCT FROM effective_amount) FROM formulas
UNION ALL
SELECT '5_framework_total', COUNT(*) FILTER (WHERE f5_applicable),
       COUNT(*) FILTER (WHERE f5_applicable AND f5 IS DISTINCT FROM effective_amount) FROM formulas
UNION ALL
SELECT '6_payments_threshold', COUNT(*),
       COUNT(*) FILTER (WHERE f6 IS DISTINCT FROM effective_amount) FROM formulas
UNION ALL
SELECT '7_feo_categories_purchase_totals', COUNT(*) FILTER (WHERE f7_applicable),
       COUNT(*) FILTER (WHERE f7_applicable AND f7 IS DISTINCT FROM effective_amount) FROM formulas
UNION ALL
SELECT '8_feo_plan_fact_amount', COUNT(*) FILTER (WHERE f8_applicable),
       COUNT(*) FILTER (WHERE f8_applicable AND f8 IS DISTINCT FROM effective_amount) FROM formulas
UNION ALL
SELECT '9_subsidies_spent', COUNT(*) FILTER (WHERE f9_applicable),
       COUNT(*) FILTER (WHERE f9_applicable AND f9 IS DISTINCT FROM effective_amount) FROM formulas
ORDER BY 1;
