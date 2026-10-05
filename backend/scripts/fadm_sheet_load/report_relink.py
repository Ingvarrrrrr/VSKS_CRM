"""Текстовый отчёт --relink (см. relink.RelinkResult)."""
from __future__ import annotations

from .relink import RelinkResult


def render_relink_report(result: RelinkResult, dry_run: bool) -> str:
    rc = result.relink_counters
    dc = result.doc_counters
    lines: list[str] = []
    mode = "DRY-RUN (откат в конце)" if dry_run else "COMMIT"
    lines.append(f"=== --relink «{result.target.name}» (id={result.target.id}) — {mode} ===")
    lines.append("")
    lines.append(f"Закупок привязано позиционно: {len(result.pairs)}")
    lines.append("")

    if result.ensured_employees:
        lines.append("--ensure-employee:")
        for r in result.ensured_employees:
            status = "заведён" if r.created else "уже был"
            lines.append(f"  - {r.user.full_name} (user#{r.user.id}, {status})")
        lines.append("")

    lines.append("Исполнитель:")
    lines.append(f"  авансовых (признак + исполнитель = сотрудник): {rc.advance_count}")
    lines.append(f"  от двойника: {rc.from_twin_count}")
    lines.append(f"  пусто (нет двойника, не авансовый): {rc.empty_count}")
    lines.append(f"  голов рамочных пересчитано: {rc.framework_heads_fixed}")
    if rc.kept_admin_from_twin_count:
        lines.append(f"  Администратор оставлен (он и есть исполнитель двойника): {rc.kept_admin_from_twin_count}")
    if rc.advance_ambiguous:
        lines.append(f"  ⚠️ ФИО совпало с >1 сотрудником (НЕ авансовый, уточните вручную): {len(rc.advance_ambiguous)}")
        for label in rc.advance_ambiguous:
            lines.append(f"    - {label}")
    lines.append("")

    lines.append(f"Авансовые отчёты ({len(rc.advance_entries)}):")
    for e in rc.advance_entries:
        lines.append(f"  - {e.label} → сотрудник user#{e.employee_user_id}, закупка id={e.purchase_id}, "
                     f"контрагент={'id=' + str(e.contractor_id) if e.contractor_id else '(пусто)'}")
    lines.append("")

    lines.append(f"Статус заказов рамочных contracted→ordered: {len(rc.framework_statuses_fixed)}")
    if rc.framework_statuses_fixed:
        lines.append("  id: " + ", ".join(str(i) for i in rc.framework_statuses_fixed))
    lines.append("")

    lines.append("Контрагенты-сотрудники (заведены загрузчиком по ФИО из таблицы):")
    lines.append(f"  удалено (больше нигде не используются): {len(rc.employees_contractors_deleted)}")
    for cid, name in rc.employees_contractors_deleted:
        lines.append(f"    - id={cid} «{name}»")
    lines.append(f"  оставлено (используются ещё где-то): {len(rc.employees_contractors_kept)}")
    for cid, name, refs in rc.employees_contractors_kept:
        lines.append(f"    - id={cid} «{name}» — {refs}")
    lines.append("")

    lines.append("Документы (двойник → новая закупка):")
    lines.append(f"  файлов скопировано: {dc.files_copied} (пропущено как уже существующие: {dc.files_skipped_existing})")
    if dc.by_file_type:
        for ft, n in sorted(dc.by_file_type.items(), key=lambda kv: -kv[1]):
            lines.append(f"    {ft}: {n}")
    lines.append(f"  чеков скопировано: {dc.receipts_copied} (пропущено как уже существующие: {dc.receipts_skipped_existing})")
    lines.append(f"  закупок с хотя бы одним скопированным документом/чеком: {dc.pairs_with_docs}")
    lines.append("")

    unmatched = [e for e, _p in result.pairs if e.twin is None]
    if unmatched:
        lines.append(f"Несвязанные единицы (нет двойника в старой субсидии, {len(unmatched)}):")
        for e in unmatched:
            lines.append(f"  - {e.label}")
        lines.append("")

    return "\n".join(lines)
