# REQUIREMENTS.md — VSKS_CRM

## v1 Requirements

### Purchase Management (PURCHASE)

- [ ] **PURCHASE-01**: The Purchase model must include the following new fields: `contract_number`, `contract_date`, `registry_number`, `purchase_method`, `nmck`, `contract_price`, `economy`, `price_increase`, `execution_term`, `execution_term_changed`, `country_origin`, `acceptance_doc_name`, `acceptance_doc_date`, `acceptance_doc_number`, `acceptance_doc_amount`, `payment_doc_number`, `payment_doc_date`, `payment_amount`, `payment_federal`. All fields must be persisted in PostgreSQL without breaking existing ФАДМ_2026 rows.
- [ ] **PURCHASE-02**: The purchase creation/edit form must expose all new fields from PURCHASE-01 in a structured layout with appropriate input types (date pickers, number inputs, text inputs).
- [ ] **PURCHASE-03**: `purchase_method` must be a dropdown with exactly two options: "Единственный исполнитель" and "Конкурсная процедура".
- [ ] **PURCHASE-04**: `economy` must be auto-calculated as `nmck - contract_price` and displayed read-only in the form; it must update in real time when either input changes.
- [ ] **PURCHASE-05**: A purchase must have a `status` field supporting the workflow: `planned → confirmed → contracted → delivered → paid`. No other status values are allowed.
- [ ] **PURCHASE-06**: Status transitions must be strictly forward-only. Backward transitions are blocked for Manager and Viewer roles; Admin may reverse a status via an explicit override action.
- [ ] **PURCHASE-07**: Transition `planned → confirmed` requires role Manager or Admin. No required field guard.
- [ ] **PURCHASE-08**: Transition `confirmed → contracted` requires role Manager or Admin AND non-empty `contract_number` + `contract_date`; the API must return HTTP 422 if those fields are absent.
- [ ] **PURCHASE-09**: Transition `contracted → delivered` requires role Manager or Admin AND non-empty `acceptance_doc_name`, `acceptance_doc_date`, `acceptance_doc_number`, `acceptance_doc_amount`; API returns HTTP 422 if absent.
- [ ] **PURCHASE-10**: Transition `delivered → paid` requires role Manager or Admin AND non-empty `payment_doc_number`, `payment_doc_date`, `payment_amount`; API returns HTTP 422 if absent.
- [ ] **PURCHASE-11**: The API endpoint `POST /api/purchases/{id}/transition?status={target}` must implement the transition logic from PURCHASE-06 through PURCHASE-10 and return the updated purchase object on success.
- [ ] **PURCHASE-12**: The purchase list view must display the current status with a color-coded chip/badge and allow filtering by status.
- [ ] **PURCHASE-13**: The purchase detail/edit view must display an action button for the next valid status transition, disabled when the current user's role is insufficient or required fields are missing.

### FEO Category Management (FEO)

- [ ] **FEO-01**: The FEO category selector in the purchase form must be a 3-level cascading dropdown: Level 1 (Направление расходов) → Level 2 (Тип расходов) → Level 3 (Конкретизированный).
- [ ] **FEO-02**: Level 2 options must be filtered to only show children of the selected Level 1 value; Level 3 options must be filtered to only show children of the selected Level 2 value.
- [ ] **FEO-03**: When the Level 1 selection changes, Level 2 and Level 3 selectors must be cleared automatically.
- [ ] **FEO-04**: When the Level 2 selection changes, Level 3 selector must be cleared automatically.
- [ ] **FEO-05**: The selected Level 3 category ID must be saved as `feo_category_id` on the purchase record.
- [ ] **FEO-06**: The "Add FEO category" button visible in the UI must open a form that allows creating a new FEO category at any level (1, 2, or 3) and persist it to the database.
- [ ] **FEO-07**: The FEO category API must return the full hierarchy in a single request so the frontend can populate all three levels without additional round trips.

### Budget Control (BUDGET)

- [ ] **BUDGET-01**: When creating or editing a purchase, the system must calculate the remaining budget for the selected subsidy as: `subsidy.limit - SUM(planned_total_price of all purchases with same subsidy_id excluding current)`.
- [ ] **BUDGET-02**: The purchase form must display a real-time budget indicator showing "Остаток: X ₽" when within limit or "Превышение на: Y ₽" when over limit, updating whenever `planned_total_price` or the subsidy selection changes.
- [ ] **BUDGET-03**: Saving a purchase (create or update) must be blocked when the new total would exceed the subsidy limit, returning HTTP 422 with a descriptive error message.
- [ ] **BUDGET-04**: Admin role must be able to bypass the budget block (override) by confirming an explicit warning dialog; the override must be logged.
- [ ] **BUDGET-05**: Budget check must also be performed at the FEO Level 3 category level: the system must show remaining budget for the selected `feo_category_id` separately from the subsidy-level check.
- [ ] **BUDGET-06**: Framework-limited contracts (see CONTRACT-03) must also be checked: the system must warn when purchases assigned to such a contract would exceed `contract.max_amount`, blocking save for Manager/Viewer.
- [x] **BUDGET-07**: The budget history table `budget_history` (already in DB) must be connected: every change to a subsidy's limit or a purchase's `planned_total_price` must write a record to `budget_history` with `changed_at`, `changed_by`, `old_value`, `new_value`, `reason`.
- [x] **BUDGET-08**: API endpoint `GET /api/subsidies/{id}/history` must return paginated records from `budget_history` for the given subsidy.
- [ ] **BUDGET-09**: The subsidy detail view must include a timeline/modal showing budget history from BUDGET-07/08.

### Contract Registry (CONTRACT)

- [ ] **CONTRACT-01**: The Contract model must support a `contract_type` field with three values: `one-time`, `framework-unlimited`, `framework-limited`.
- [ ] **CONTRACT-02**: For `contract_type = one-time`: the contract is linked to a single purchase; total contract value equals the purchase `planned_total_price`.
- [ ] **CONTRACT-03**: For `contract_type = framework-limited`: a `max_amount` field stores the spending ceiling; `current_amount` (read-only, computed) equals the sum of all linked purchases' `planned_total_price`.
- [ ] **CONTRACT-04**: For `contract_type = framework-unlimited`: no spending ceiling; `current_amount` is still computed and displayed for informational purposes.
- [ ] **CONTRACT-05**: The contract list/detail view must display `current_amount`, `max_amount` (if applicable), and a utilization percentage bar.
- [ ] **CONTRACT-06**: When a framework-limited contract reaches >90% utilization, the UI must display a warning indicator on the contract card and in the purchase form when that contract is selected.
- [ ] **CONTRACT-07**: The contract registry must support filtering by `contract_type`, contractor, and subsidy.

### File Attachments (FILES)

- [ ] **FILES-01**: The API endpoint `POST /api/purchases/{id}/files` must accept multipart file upload and store the file as `bytea` in the `purchase_files` table (already exists in DB) with fields: `purchase_id`, `filename` (UUID-based), `original_name`, `mime_type`, `file_size`, `file_data`, `uploaded_at`, `description`.
- [ ] **FILES-02**: Accepted MIME types are: `application/pdf`, `image/jpeg`, `image/png`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`. Other types must be rejected with HTTP 415.
- [ ] **FILES-03**: The API endpoint `GET /api/purchases/{id}/files` must return a list of file metadata (without `file_data`) for all files attached to the given purchase.
- [ ] **FILES-04**: The API endpoint `GET /api/purchases/{id}/files/{file_id}` must stream the file binary with correct `Content-Type` and `Content-Disposition: attachment; filename="original_name"` headers.
- [ ] **FILES-05**: The purchase detail view must display a file attachment panel showing the list of attached files (name, size, date, description) with Download and Delete actions.
- [ ] **FILES-06**: All three roles (Admin, Manager, Viewer) may upload and download files. Only Admin and Manager may delete files.
- [ ] **FILES-07**: The delete endpoint `DELETE /api/purchases/{id}/files/{file_id}` must hard-delete the record from `purchase_files` and return HTTP 204.

### Export / Import (EXPORT)

- [ ] **EXPORT-01**: The API endpoint `GET /api/purchases/export?subsidy_id=X&year=Y` must generate and stream an `.xlsx` file using openpyxl with column layout matching the GoodsService sheet format from the client's Google Sheets template.
- [ ] **EXPORT-02**: The export must include all purchase fields relevant to the GoodsService format: at minimum registry_number, name, purchase_method, contractor, contract_number, contract_date, nmck, contract_price, economy, feo category path, subsidy name, status, payment amounts.
- [ ] **EXPORT-03**: The export file must be downloadable directly from a button in the Subsidies or Purchases UI without navigating away.
- [ ] **EXPORT-04**: The API endpoint `POST /api/payments/import` must accept a CSV or `.xlsx` file (Scroller sheet format), parse rows, match each row to an existing purchase by contract number or contractor name, and update `payment_amount`, `payment_doc_number`, `payment_doc_date` on the matched purchase.
- [ ] **EXPORT-05**: The import endpoint must return a summary response: `{imported: N, skipped: M, errors: [{row, reason}]}`. Rows that cannot be matched must not cause a server error; they must be reported in `errors`.
- [ ] **EXPORT-06**: The import UI must allow file selection, show a preview summary after upload, and confirm before applying changes.

### Roles and Navigation (ROLES)

- [ ] **ROLES-01**: Admin role must have access to all navigation sections: Dashboard, Subsidies, Purchases, Contractors, Contracts, Payments, FEO Categories, Wishes, User Management.
- [ ] **ROLES-02**: Manager role must have access to: Dashboard, Subsidies, Purchases, Contractors, Contracts, Payments. Manager must not see User Management or FEO category admin.
- [ ] **ROLES-03**: Viewer (employee) role must see only the "Мои заявки" (Wishes) section in navigation. All other sections must be inaccessible (return HTTP 403 from API if accessed directly).
- [ ] **ROLES-04**: Navigation sidebar must render only the links permitted for the current user's role; forbidden links must not appear at all (not just disabled).
- [ ] **ROLES-05**: The Vue Router must enforce role-based route guards: navigating to a forbidden route must redirect to the user's default landing page.
- [ ] **ROLES-06**: All API endpoints must enforce role checks server-side using JWT claims; role enforcement must not rely solely on frontend guards.

### Wishes Workflow (WISHES)

- [ ] **WISHES-01**: The `wishes` table (already in DB) must be connected to a backend model `Wish` with fields: `id`, `title`, `description`, `requested_by` (user_id), `status` (`draft → submitted → approved → rejected → converted`), `created_at`, `updated_at`, `purchase_id` (nullable, set when converted).
- [ ] **WISHES-02**: Viewer role must be able to create a new Wish via a form with fields: `title` (required), `description` (optional). Initial status is `draft`.
- [ ] **WISHES-03**: Viewer must be able to submit a draft Wish (transition `draft → submitted`); only the creator may submit their own wish.
- [ ] **WISHES-04**: Manager or Admin may approve a submitted Wish (`submitted → approved`) or reject it (`submitted → rejected`) with an optional rejection reason.
- [ ] **WISHES-05**: When a Wish is approved, an Admin or Manager may convert it to a Purchase (`approved → converted`): this creates a new Purchase record pre-populated with `title` and `description` from the wish and sets `wish.purchase_id` to the new purchase's ID.
- [ ] **WISHES-06**: The "Мои заявки" page must show the Viewer's own wishes with current status and, for approved/converted wishes, a link to the resulting purchase.
- [ ] **WISHES-07**: Managers and Admins must have a "Заявки сотрудников" view showing all submitted wishes with approve/reject actions.

---

## v2 Requirements (Deferred)

- **OCR**: Automatic text extraction from uploaded PDFs using pytesseract or external OCR API — deferred until client provides sample documents.
- **DOCX Generation**: Auto-generation of service notes and approval sheets using python-docx + Jinja2 templates — deferred until Igor provides contract templates.
- **n8n Notifications**: Webhook-triggered notifications (email/Telegram) on status transitions — infrastructure exists (n8n running), implementation deferred.
- **Drill-down Dashboard**: Click-through FEO category breakdown in charts (BudgetDrillDownDialog partially implemented) — deferred to analytics phase.
- **ЕИС Integration**: Integration with zakupki.gov.ru — explicitly out of scope for v1.

---

## Out of Scope

- OCR PDF-документов (pytesseract / external API) — отложено.
- Генерация DOCX из шаблонов — заглушка; шаблоны предоставит заказчик позже.
- Мобильное приложение — не предусмотрено.
- Интеграция с ЕИС (zakupki.gov.ru) — не в текущей версии.

---

## Traceability

| REQ-ID | Phase |
|--------|-------|
| PURCHASE-01 | Phase 1 |
| PURCHASE-02 | Phase 1 |
| PURCHASE-03 | Phase 1 |
| PURCHASE-04 | Phase 1 |
| PURCHASE-05 | Phase 1 |
| PURCHASE-06 | Phase 1 |
| PURCHASE-07 | Phase 1 |
| PURCHASE-08 | Phase 1 |
| PURCHASE-09 | Phase 1 |
| PURCHASE-10 | Phase 1 |
| PURCHASE-11 | Phase 1 |
| PURCHASE-12 | Phase 1 |
| PURCHASE-13 | Phase 1 |
| FEO-01 | Phase 2 |
| FEO-02 | Phase 2 |
| FEO-03 | Phase 2 |
| FEO-04 | Phase 2 |
| FEO-05 | Phase 2 |
| FEO-06 | Phase 2 |
| FEO-07 | Phase 2 |
| BUDGET-01 | Phase 2 |
| BUDGET-02 | Phase 2 |
| BUDGET-03 | Phase 2 |
| BUDGET-04 | Phase 2 |
| BUDGET-05 | Phase 2 |
| BUDGET-06 | Phase 4 |
| BUDGET-07 | Phase 6 |
| BUDGET-08 | Phase 6 |
| BUDGET-09 | Phase 6 |
| FILES-01 | Phase 3 |
| FILES-02 | Phase 3 |
| FILES-03 | Phase 3 |
| FILES-04 | Phase 3 |
| FILES-05 | Phase 3 |
| FILES-06 | Phase 3 |
| FILES-07 | Phase 3 |
| CONTRACT-01 | Phase 4 |
| CONTRACT-02 | Phase 4 |
| CONTRACT-03 | Phase 4 |
| CONTRACT-04 | Phase 4 |
| CONTRACT-05 | Phase 4 |
| CONTRACT-06 | Phase 4 |
| CONTRACT-07 | Phase 4 |
| EXPORT-01 | Phase 5 |
| EXPORT-02 | Phase 5 |
| EXPORT-03 | Phase 5 |
| EXPORT-04 | Phase 5 |
| EXPORT-05 | Phase 5 |
| EXPORT-06 | Phase 5 |
| ROLES-01 | Phase 7 |
| ROLES-02 | Phase 7 |
| ROLES-03 | Phase 7 |
| ROLES-04 | Phase 7 |
| ROLES-05 | Phase 7 |
| ROLES-06 | Phase 7 |
| WISHES-01 | Phase 7 |
| WISHES-02 | Phase 7 |
| WISHES-03 | Phase 7 |
| WISHES-04 | Phase 7 |
| WISHES-05 | Phase 7 |
| WISHES-06 | Phase 7 |
| WISHES-07 | Phase 7 |
