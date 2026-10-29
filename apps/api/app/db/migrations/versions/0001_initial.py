"""initial schema, pgvector, row-level security, least-privilege grants

Revision ID: 0001
Revises:
"""
from alembic import op

from app.db.base import Base
from app.models import tables  # noqa: F401

revision = "0001"
down_revision = None

# Tables whose rows belong to exactly one org and are readable only inside that org's context.
TENANT_TABLES = ["memberships", "repositories", "build_events", "alert_channels", "embeddings"]
APP_ROLE = "releaseradar_app"  # runtime role: NOT the table owner, so RLS cannot be bypassed by it


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=bind)
    op.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            id bigserial PRIMARY KEY,
            org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            source varchar(100) NOT NULL,
            content text NOT NULL,
            embedding vector(1536) NOT NULL
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS embeddings_org_idx ON embeddings (org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS embeddings_vec_idx ON embeddings USING hnsw (embedding vector_cosine_ops)")

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (org_id = NULLIF(current_setting('app.current_org', true), '')::uuid)
            WITH CHECK (org_id = NULLIF(current_setting('app.current_org', true), '')::uuid)""")

    op.execute(f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} LOGIN;   -- set its password out-of-band from your secret store
            END IF;
        END $$""")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    # Audit log is append-only for the runtime role.
    op.execute(f"REVOKE UPDATE, DELETE ON audit_log FROM {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS embeddings")
    Base.metadata.drop_all(bind=op.get_bind())
