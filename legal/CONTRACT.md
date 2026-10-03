# Контракт сборки правовых документов GALA

Этот файл задаёт границы между частями работы. Менять его может только основная сессия.

## Принцип (ПРАВИЛО №6)

`legal/operator.json` — **единственное** место, где живут реквизиты оператора, домен, почта,
сроки по 152-ФЗ, состав обрабатываемых данных и версии документов. Ни в одном тексте документа,
ни в одном компоненте фронта, ни в одном приказе реквизит не написан буквами — только подстановка.

Пока юрлицо не зарегистрировано и домен не куплен, значения выглядят как `{{ИНН}}`. Это нормально:
сборка проходит, документы читаются, плейсхолдеры видны глазом. После заполнения `operator.json`
и `python legal/build.py` они исчезают везде одновременно.

## Раскладка

```
legal/
  operator.json              единственный источник (НЕ трогать исполнителям)
  CONTRACT.md                этот файл
  build.py                   сборщик: markdown + operator.json -> фронт, бэкенд и .docx
  sources/public/*.md        тексты публичных документов
  sources/internal/*.md      тексты внутренних приказов и положений
  out/                       сгенерированные .docx (git-ignored)
frontend/src/legal/
  documents.generated.ts     СГЕНЕРИРОВАН build.py, править руками запрещено
backend/app/services/
  legal_generated.py         СГЕНЕРИРОВАН build.py, править руками запрещено
```

Сборка производит ДВА артефакта, и оба коммитятся в репозиторий: один для
фронтенда (`documents.generated.ts`), один для бэкенда (`legal_generated.py`).
Второй существует потому, что образ бэкенда собирается только из каталога
`backend/` и не видит `legal/` — константы 152-ФЗ, нужные
`backend/app/services/legal_constants.py`, обязаны лежать рядом с кодом
бэкенда, а не читаться с диска по пути к `legal/operator.json`.

## Язык шаблонов

В markdown-исходниках допустимы только эти подстановки, синтаксис — двойные фигурные скобки
с точечным путём внутрь `operator.json`:

```
{{operator.full_name}}   {{operator.inn}}        {{operator.legal_address}}
{{head.fio}}             {{head.position}}       {{responsible.email}}
{{site.url}}             {{site.product_name}}   {{site.support_email}}
{{hosting.provider}}     {{consent.term_months}}
{{deadlines_working_days.info_request}}
{{doc.title}}            {{doc.version}}         {{doc.effective_date}}
{{today}}
```

Дополнительно доступен фильтр сокращения ФИО (память проекта: «Фамилия И.О.»,
идемпотентно): `{{head.fio|short}}`.

Список `processing.sensitive_fields` и `processing.subjects` разворачивается в маркированный
список через `{{#each processing.sensitive_fields}}`.

Неизвестная подстановка — **ошибка сборки**, а не пустая строка. Молчаливый пропуск в правовом
документе опаснее падения.

## Что генерирует build.py

1. `frontend/src/legal/documents.generated.ts` — только документы с `kind: "public"`:

```ts
export interface LegalDoc {
  slug: string
  route: string
  title: string
  version: string
  effectiveDate: string
  html: string          // отрендеренный markdown, без <script>
}
export const LEGAL_DOCS: Record<string, LegalDoc>
export const LEGAL_DOC_LIST: LegalDoc[]
export const LEGAL_VERSION: string   // общая версия комплекта, для записи согласий
export const OPERATOR: { fullName: string; inn: string; ogrn: string; legalAddress: string; supportEmail: string; legalEmail: string; siteUrl: string; filled: boolean }
```

2. `backend/app/services/legal_generated.py` — константы, нужные бэкенду:

```py
DEADLINES_WORKING_DAYS: dict[str, int]           # из operator.json -> deadlines_working_days
REGISTRATION_CONSENT_DOCUMENTS: tuple[str, ...]  # из build.py -> REGISTRATION_CONSENT_SLUGS
```

Ровно эти два блока — не тащить в файл лишнее из `operator.json` «на будущее»; новая
потребность бэкенда добавляется здесь явно, вместе с местом, которое её реально использует.

3. `legal/out/<slug>.docx` — все документы, публичные и внутренние. Внутренние — с шапкой
организации, местом для номера, даты и подписи.

Сборка **идемпотентна**: повторный запуск без изменений даёт байт-идентичный результат
(как `backend/templates/build/`). Проверяется sha256. `python legal/build.py --check`
ловит расхождение для всех трёх артефактов (TS, PY, .docx).

## Границы работ (кто чего не касается)

| Участок | Файлы | Не трогает |
|---|---|---|
| Сборщик и публичные тексты | `legal/build.py`, `legal/sources/public/*` | всё остальное |
| Внутренние документы | `legal/sources/internal/*` | `build.py`, фронт, бэкенд |
| Фронтенд | `frontend/src/legal/*` (кроме generated), `views/legal/*`, `components/legal/*`, роутер, `RegisterView.vue`, `LandingView.vue` | `legal/`, бэкенд |
| Бэкенд согласий | `backend/app/models/user_consent.py`, `backend/app/routers/legal.py`, `backend/app/services/legal_constants.py`, миграция | фронт, `legal/` |

`documents.generated.ts` и `backend/app/services/legal_generated.py` пишет только `build.py`.
Фронтенд импортирует первый и никогда не правит; `legal_constants.py` импортирует второй и
никогда не правит — оба генерируемых файла коммитятся в репозиторий.

## Отдельно про факт согласия

Согласие — юридический факт, а не галочка в интерфейсе. Фиксируется на сервере: кто, когда,
с какого адреса, каким браузером, на какую **версию** комплекта (`LEGAL_VERSION`). Без версии
запись бесполезна: через год нельзя будет доказать, с чем именно человек согласился.
