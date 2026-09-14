"""feo_comments + feo_comments_visibility — комментарии (мини-чат) к плановым
позициям ФЭО и категориям дерева ФЭО.

Владелец, Волна 4, п.16 (2026-09-13): «Должна быть возможность оставлять
комментарии, которые тоже видны постоянно (переключатель делать, для
видимости комментариев, сразу для всей субсидии)... отображается, кто
оставил комментарий и когда, и текст комментария, и на него должна быть
возможность ответить». Область — плановые позиции (feo_planned_items) и
узлы дерева ФЭО (feo_categories); закупки/договоры в эту волну не входят.

Создаёт (идемпотентно, под insp.has_table() guard, по образцу
r4t6v8x0z2b4_staff_location_requests.py):

  feo_comments:
    feo_planned_item_id  FK feo_planned_items(id) ON DELETE CASCADE, NULL
    feo_category_id      FK feo_categories(id) ON DELETE CASCADE, NULL
    CHECK: ровно одна из двух колонок выше заполнена — см. докстринг
      app/models/feo_comment.py::FeoComment про выбор ДВУХ настоящих FK
      вместо полиморфной пары entity_type/entity_id (гарантия отсутствия
      висячих комментариев средствами самой БД, без ручной чистки в каждом
      месте удаления позиции/категории).
    parent_id            FK feo_comments(id) ON DELETE CASCADE, NULL — ответ
      на другой комментарий той же ветки.
    user_id               FK users(id) ON DELETE SET NULL, NULL
    author_name           VARCHAR(255) NULL — снимок ФИО на момент публикации
    text                  TEXT NOT NULL
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()

  feo_comments_visibility:
    subsidy_id           FK subsidies(id) ON DELETE CASCADE, PRIMARY KEY
    comments_visible     BOOLEAN NOT NULL DEFAULT true
    Одна строка на субсидию; отсутствие строки трактуется приложением как
    comments_visible=True (см. get_comments_visibility в
    app/routers/feo_comments.py) — отдельная таблица, а не колонка на
    Subsidy, т.к. backend/app/models/subsidy.py в этой волне занят другим
    исполнителем (файл вне списка разрешённых для этой задачи).

Revision ID: 8f3db1cb5c70
Revises: q8s0u2w4y6a8
Create Date: 2026-09-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '8f3db1cb5c70'
down_revision = 'q8s0u2w4y6a8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table("feo_comments"):
        op.create_table(
            "feo_comments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("feo_planned_item_id", sa.Integer(),
                      sa.ForeignKey("feo_planned_items.id", ondelete="CASCADE"), nullable=True),
            sa.Column("feo_category_id", sa.Integer(),
                      sa.ForeignKey("feo_categories.id", ondelete="CASCADE"), nullable=True),
            sa.Column("parent_id", sa.Integer(),
                      sa.ForeignKey("feo_comments.id", ondelete="CASCADE"), nullable=True),
            sa.Column("user_id", sa.Integer(),
                      sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("author_name", sa.String(255), nullable=True),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.text("now()"), nullable=False),
            sa.CheckConstraint(
                "(feo_planned_item_id IS NOT NULL AND feo_category_id IS NULL) OR "
                "(feo_planned_item_id IS NULL AND feo_category_id IS NOT NULL)",
                name="ck_feo_comment_exactly_one_target",
            ),
        )
        op.create_index("ix_feo_comments_feo_planned_item_id", "feo_comments", ["feo_planned_item_id"])
        op.create_index("ix_feo_comments_feo_category_id", "feo_comments", ["feo_category_id"])
        op.create_index("ix_feo_comments_parent_id", "feo_comments", ["parent_id"])
        print("[8f3db1cb5c70] feo_comments создана")

    if not insp.has_table("feo_comments_visibility"):
        op.create_table(
            "feo_comments_visibility",
            sa.Column("subsidy_id", sa.Integer(),
                      sa.ForeignKey("subsidies.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("comments_visible", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )
        print("[8f3db1cb5c70] feo_comments_visibility создана")


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS feo_comments_visibility"))
    op.execute(sa.text("DROP TABLE IF EXISTS feo_comments"))
