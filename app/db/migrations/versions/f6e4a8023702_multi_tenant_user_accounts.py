"""multi_tenant_user_accounts

Revision ID: f6e4a8023702
Revises: 99ba3a43d7f1
Create Date: 2026-11-16 22:10:31.181720

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6e4a8023702'
down_revision: Union[str, Sequence[str], None] = '99ba3a43d7f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema with SQLite batch alteration safety."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # 1. Create 'users' table if not exists
    if "users" not in existing_tables:
        op.create_table(
            'users',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('email', sa.String(length=255), nullable=False),
            sa.Column('hashed_password', sa.String(length=255), nullable=True),
            sa.Column('full_name', sa.String(length=255), nullable=True),
            sa.Column('avatar_url', sa.String(length=500), nullable=True),
            sa.Column('auth_provider', sa.String(length=50), nullable=True, server_default='local'),
            sa.Column('is_active', sa.Boolean(), nullable=True, server_default='1'),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
        op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # 2. Create 'user_job_applications' table if not exists
    if "user_job_applications" not in existing_tables:
        op.create_table(
            'user_job_applications',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('job_id', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(length=50), nullable=True, server_default='review_pending'),
            sa.Column('match_score', sa.Integer(), nullable=True),
            sa.Column('match_reason', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_user_job_applications_id'), 'user_job_applications', ['id'], unique=False)
        op.create_index(op.f('ix_user_job_applications_job_id'), 'user_job_applications', ['job_id'], unique=False)
        op.create_index(op.f('ix_user_job_applications_status'), 'user_job_applications', ['status'], unique=False)
        op.create_index(op.f('ix_user_job_applications_user_id'), 'user_job_applications', ['user_id'], unique=False)

    # 3. Batch alter candidate_profiles to add user_id
    if "candidate_profiles" in existing_tables:
        cols = [c['name'] for c in inspector.get_columns('candidate_profiles')]
        with op.batch_alter_table('candidate_profiles', recreate='auto') as batch_op:
            if 'user_id' not in cols:
                batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
                batch_op.create_index('ix_candidate_profiles_user_id', ['user_id'], unique=False)

    # 4. Batch alter answer_bank to add user_id
    if "answer_bank" in existing_tables:
        cols = [c['name'] for c in inspector.get_columns('answer_bank')]
        with op.batch_alter_table('answer_bank', recreate='auto') as batch_op:
            if 'user_id' not in cols:
                batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
                batch_op.create_index('ix_answer_bank_user_id', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('answer_bank', recreate='auto') as batch_op:
        batch_op.drop_index('ix_answer_bank_user_id')
        batch_op.drop_column('user_id')

    with op.batch_alter_table('candidate_profiles', recreate='auto') as batch_op:
        batch_op.drop_index('ix_candidate_profiles_user_id')
        batch_op.drop_column('user_id')

    op.drop_table('user_job_applications')
    op.drop_table('users')
