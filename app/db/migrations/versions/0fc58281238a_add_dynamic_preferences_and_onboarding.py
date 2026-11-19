"""add_dynamic_preferences_and_onboarding

Revision ID: 0fc58281238a
Revises: f6e4a8023702
Create Date: 2026-11-19 17:25:17.522168

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0fc58281238a'
down_revision: Union[str, Sequence[str], None] = 'f6e4a8023702'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # 1. Users table: is_onboarded
    user_cols = [c['name'] for c in inspector.get_columns('users')]
    with op.batch_alter_table('users', recreate='auto') as batch_op:
        if 'is_onboarded' not in user_cols:
            batch_op.add_column(sa.Column('is_onboarded', sa.Boolean(), nullable=True, server_default=sa.text('false')))
            
    # 2. Candidate Profiles: dynamic preference columns
    profile_cols = [c['name'] for c in inspector.get_columns('candidate_profiles')]
    with op.batch_alter_table('candidate_profiles', recreate='auto') as batch_op:
        if 'base_city' not in profile_cols:
            batch_op.add_column(sa.Column('base_city', sa.String(length=100), nullable=True, server_default=''))
        if 'base_country' not in profile_cols:
            batch_op.add_column(sa.Column('base_country', sa.String(length=100), nullable=True, server_default='India'))
        if 'target_titles_list' not in profile_cols:
            batch_op.add_column(sa.Column('target_titles_list', sa.JSON(), nullable=True))
        if 'target_cities' not in profile_cols:
            batch_op.add_column(sa.Column('target_cities', sa.JSON(), nullable=True))
        if 'work_modes' not in profile_cols:
            batch_op.add_column(sa.Column('work_modes', sa.JSON(), nullable=True))
        if 'visa_sponsorship_needed' not in profile_cols:
            batch_op.add_column(sa.Column('visa_sponsorship_needed', sa.Boolean(), nullable=True, server_default=sa.text('false')))
        if 'open_to_relocation' not in profile_cols:
            batch_op.add_column(sa.Column('open_to_relocation', sa.Boolean(), nullable=True, server_default=sa.text('false')))


def downgrade() -> None:
    with op.batch_alter_table('candidate_profiles', recreate='auto') as batch_op:
        batch_op.drop_column('open_to_relocation')
        batch_op.drop_column('visa_sponsorship_needed')
        batch_op.drop_column('work_modes')
        batch_op.drop_column('target_cities')
        batch_op.drop_column('target_titles_list')
        batch_op.drop_column('base_country')
        batch_op.drop_column('base_city')
        
    with op.batch_alter_table('users', recreate='auto') as batch_op:
        batch_op.drop_column('is_onboarded')
