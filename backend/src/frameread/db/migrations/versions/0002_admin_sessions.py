from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE admin_sessions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            deleted_at timestamptz NULL,
            version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
            token_hash bytea NOT NULL UNIQUE CHECK (octet_length(token_hash) = 32),
            csrf_hash bytea NOT NULL CHECK (octet_length(csrf_hash) = 32),
            credential_generation text NOT NULL CHECK (credential_generation ~ '^[0-9a-f]{16}$'),
            expires_at timestamptz NOT NULL,
            last_seen_at timestamptz NOT NULL
        )
    """)
    op.execute("CREATE INDEX admin_sessions_expires_at_idx ON admin_sessions (expires_at)")
    op.execute(
        "CREATE TRIGGER admin_sessions_touch BEFORE UPDATE ON admin_sessions "
        "FOR EACH ROW EXECUTE FUNCTION frameread_touch_updated_at()"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON admin_sessions TO frameread_app")


def downgrade() -> None:
    raise NotImplementedError
