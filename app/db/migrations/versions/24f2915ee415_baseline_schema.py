"""baseline_schema

Revision ID: 24f2915ee415
Revises: 
Create Date: 2026-11-03 02:03:57.542651

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import app.core.security
from app.core.security import set_keyring_secret, mask_secret, KEYRING_SERVICE_VAULT

# revision identifiers, used by Alembic.
revision: str = '24f2915ee415'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Step 1: Migrate existing plaintext keys to OS Keyring if present
    # Check if api_key column exists in ai_keys
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('ai_keys')]
    
    if 'api_key' in columns:
        rows = conn.execute(sa.text("SELECT id, api_key FROM ai_keys")).fetchall()
        for row in rows:
            row_id, plaintext_key = row[0], row[1]
            if plaintext_key:
                k_id = f"ai_key_{row_id}"
                set_keyring_secret(KEYRING_SERVICE_VAULT, k_id, plaintext_key)

    # Step 2: Batch alter ai_keys for SQLite compatibility
    with op.batch_alter_table('ai_keys', recreate='auto') as batch_op:
        if 'keyring_id' not in columns:
            batch_op.add_column(sa.Column('keyring_id', sa.String(length=150), nullable=True))
        if 'api_key_masked' not in columns:
            batch_op.add_column(sa.Column('api_key_masked', sa.String(length=50), nullable=True))

    # Populate keyring_id and api_key_masked for migrated rows
    if 'api_key' in columns:
        rows = conn.execute(sa.text("SELECT id, api_key FROM ai_keys")).fetchall()
        for row in rows:
            row_id, plaintext_key = row[0], row[1]
            k_id = f"ai_key_{row_id}"
            masked = mask_secret(plaintext_key) if plaintext_key else ""
            conn.execute(
                sa.text("UPDATE ai_keys SET keyring_id = :kid, api_key_masked = :masked WHERE id = :id"),
                {"kid": k_id, "masked": masked, "id": row_id}
            )

    # Now drop api_key and enforce constraints
    with op.batch_alter_table('ai_keys', recreate='auto') as batch_op:
        if 'api_key' in columns:
            batch_op.drop_column('api_key')
        batch_op.create_unique_constraint('uq_ai_keys_keyring_id', ['keyring_id'])

    # Step 3: Batch alter candidate_profiles
    profile_cols = [c['name'] for c in inspector.get_columns('candidate_profiles')]
    with op.batch_alter_table('candidate_profiles', recreate='auto') as batch_op:
        batch_op.alter_column('email',
                              existing_type=sa.VARCHAR(length=200),
                              type_=app.core.security.EncryptedText(),
                              existing_nullable=True)
        batch_op.alter_column('phone',
                              existing_type=sa.VARCHAR(length=50),
                              type_=app.core.security.EncryptedText(),
                              existing_nullable=True)
        batch_op.alter_column('expected_salary',
                              existing_type=sa.VARCHAR(length=100),
                              type_=app.core.security.EncryptedText(),
                              existing_nullable=True)

    # Step 4: Batch alter jobs
    jobs_cols = [c['name'] for c in inspector.get_columns('jobs')]
    with op.batch_alter_table('jobs', recreate='auto') as batch_op:
        if 'remote_type' not in jobs_cols:
            batch_op.add_column(sa.Column('remote_type', sa.String(length=50), nullable=True, server_default='unknown'))
        if 'eligibility_status' not in jobs_cols:
            batch_op.add_column(sa.Column('eligibility_status', sa.String(length=50), nullable=True, server_default='eligible'))
            batch_op.create_index('ix_jobs_eligibility_status', ['eligibility_status'], unique=False)
        if 'eligibility_evidence' not in jobs_cols:
            batch_op.add_column(sa.Column('eligibility_evidence', sa.Text(), nullable=True))
        if 'regions_allowed' not in jobs_cols:
            batch_op.add_column(sa.Column('regions_allowed', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('jobs', recreate='auto') as batch_op:
        batch_op.drop_index('ix_jobs_eligibility_status')
        batch_op.drop_column('regions_allowed')
        batch_op.drop_column('eligibility_evidence')
        batch_op.drop_column('eligibility_status')
        batch_op.drop_column('remote_type')

    with op.batch_alter_table('candidate_profiles', recreate='auto') as batch_op:
        batch_op.alter_column('expected_salary',
                              existing_type=app.core.security.EncryptedText(),
                              type_=sa.VARCHAR(length=100),
                              existing_nullable=True)
        batch_op.alter_column('phone',
                              existing_type=app.core.security.EncryptedText(),
                              type_=sa.VARCHAR(length=50),
                              existing_nullable=True)
        batch_op.alter_column('email',
                              existing_type=app.core.security.EncryptedText(),
                              type_=sa.VARCHAR(length=200),
                              existing_nullable=True)

    with op.batch_alter_table('ai_keys', recreate='auto') as batch_op:
        batch_op.add_column(sa.Column('api_key', sa.VARCHAR(length=500), nullable=True))
        batch_op.drop_constraint('uq_ai_keys_keyring_id', type_='unique')
        batch_op.drop_column('api_key_masked')
        batch_op.drop_column('keyring_id')
