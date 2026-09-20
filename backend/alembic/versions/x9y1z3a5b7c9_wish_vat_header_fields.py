"""НДС для заявки: vat_applicable/vat_rate/vat_exemption_article на wishes

Владелец (жалоба, 2026-09-17): «ничего не могу ввести ничего в НДС, ни
процент, ни "Не облагается", т.к. потом не даёт объяснение вписать почему не
облагается» — при режиме vat_mode='uniform' (единая ставка на всю заявку)
блок НДС (PurchaseVatBlock.vue) рисовался в форме заявки, но wishes хранит
ТОЛЬКО vat_mode — самих значений (облагается ли, какая ставка, какая статья
НК РФ) на заявке было негде хранить. WishFormDialog.vue не пробрасывал
:vat-applicable/:vat-rate/:vat-exemption-article вовсе — любой ввод в блоке
пропадал при следующей перерисовке, что и выглядело как «ничего не могу
ввести».

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS), зеркалируя
purchases.vat_applicable/vat_rate/vat_exemption_article один в один:
  wishes:
    - vat_applicable        BOOLEAN      NULL — тот же смысл, что у Purchase:
      True = облагается, False = не облагается (нужна статья), NULL = «ещё не
      знаю» (осознанный третий выбор в дропдауне «Ставка НДС», см.
      PurchaseVatBlock.vue::UNKNOWN — контрагент на этапе заявки часто ещё не
      выбран, решение по НДС откладывается без блокировки заявки).
    - vat_rate               INTEGER      NULL — ставка (0/5/7/10/20/22).
    - vat_exemption_article  VARCHAR(200) NULL — статья НК РФ, необязательна
      на этапе заявки (см. PurchaseVatBlock::requireArticle/isWishStage).

Существующие заявки — все три поля NULL («ещё не знаю»), поведение не
меняется: раньше значений и не было вовсе. При конвертации заявки в закупку
(app/services/documents/... wish→purchase) эти поля переносятся в
Purchase.vat_applicable/vat_rate/vat_exemption_article тем же кодом, что
переносит vat_mode — второй перенос не заводим.

Downgrade — DROP COLUMN IF EXISTS (идемпотентно).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'x9y1z3a5b7c9'
down_revision = 'w3x4y5z6a7b8'
branch_labels = None
depends_on = None

_COLUMNS = [
    ("vat_applicable", sa.Boolean(), True),
    ("vat_rate", sa.Integer(), True),
    ("vat_exemption_article", sa.String(200), True),
]


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("wishes")}
    for name, coltype, nullable in _COLUMNS:
        if name not in existing_cols:
            op.add_column("wishes", sa.Column(name, coltype, nullable=nullable))


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("wishes")}
    for name, _coltype, _nullable in _COLUMNS:
        if name in existing_cols:
            op.drop_column("wishes", name)
