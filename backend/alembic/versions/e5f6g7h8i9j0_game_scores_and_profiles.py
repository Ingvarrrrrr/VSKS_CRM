"""Лидерборды мини-игр окна ожидания — таблицы game_scores (личный рекорд на
игру) и game_profiles (публичный ник для глобального рейтинга), владелец,
30.10.2026 (см. app/models/game_score.py, app/routers/games.py).

down_revision = c7d9e1f3g5h7 — линейно после d4f6h8j0k2m4 и c7d9e1f3g5h7
в ветке claude (один head, без разветвления).

Идемпотентно: CREATE TABLE IF NOT EXISTS + guard через information_schema
на CHECK/UNIQUE constraint (повторный прогон безопасен).
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "e5f6g7h8i9j0"
down_revision = "c7d9e1f3g5h7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS game_scores (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            account_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
            game VARCHAR(16) NOT NULL,
            best_score INTEGER NOT NULL DEFAULT 0,
            plays INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_game_score_user_game'
            ) THEN
                ALTER TABLE game_scores
                    ADD CONSTRAINT uq_game_score_user_game UNIQUE (user_id, game);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_game_score_game_id'
            ) THEN
                ALTER TABLE game_scores
                    ADD CONSTRAINT ck_game_score_game_id
                    CHECK (game IN ('duck', 'brick', 'tank', 'egg'));
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_game_score_non_negative'
            ) THEN
                ALTER TABLE game_scores
                    ADD CONSTRAINT ck_game_score_non_negative CHECK (best_score >= 0);
            END IF;
        END $$;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_game_scores_game_best_score "
        "ON game_scores (game, best_score DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_game_scores_account_game "
        "ON game_scores (account_id, game, best_score DESC);"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS game_profiles (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            nickname VARCHAR(24)
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS game_profiles;")
    op.execute("DROP TABLE IF EXISTS game_scores;")
