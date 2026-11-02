"""structured_candidate_profile

Revision ID: 99ba3a43d7f1
Revises: 24f2915ee415
Create Date: 2026-11-03 02:12:32.706822

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import app.core.security

# revision identifiers, used by Alembic.
revision: str = '99ba3a43d7f1'
down_revision: Union[str, Sequence[str], None] = '24f2915ee415'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # 1. Candidate Identities
    if "candidate_identities" not in existing_tables:
        op.create_table(
            'candidate_identities',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('full_name', sa.String(length=200), nullable=False),
            sa.Column('email', app.core.security.EncryptedText(), nullable=False),
            sa.Column('phone', app.core.security.EncryptedText(), nullable=False),
            sa.Column('location', sa.String(length=200), nullable=True),
            sa.Column('citizenship', sa.String(length=100), nullable=True),
            sa.Column('work_authorization', sa.String(length=250), nullable=True),
            sa.Column('notice_period', sa.String(length=100), nullable=True),
            sa.Column('expected_salary', app.core.security.EncryptedText(), nullable=True),
            sa.Column('linkedin_url', sa.String(length=300), nullable=True),
            sa.Column('github_url', sa.String(length=300), nullable=True),
            sa.Column('portfolio_url', sa.String(length=300), nullable=True),
            sa.Column('summary', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_candidate_identities_id'), 'candidate_identities', ['id'], unique=False)

    # 2. Work Experiences
    if "work_experiences" not in existing_tables:
        op.create_table(
            'work_experiences',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('candidate_id', sa.Integer(), nullable=True),
            sa.Column('company', sa.String(length=200), nullable=False),
            sa.Column('title', sa.String(length=200), nullable=False),
            sa.Column('location', sa.String(length=150), nullable=True),
            sa.Column('is_remote', sa.Boolean(), nullable=True),
            sa.Column('start_date', sa.String(length=50), nullable=False),
            sa.Column('end_date', sa.String(length=50), nullable=True),
            sa.Column('is_current', sa.Boolean(), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('bullet_points', sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(['candidate_id'], ['candidate_identities.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_work_experiences_id'), 'work_experiences', ['id'], unique=False)
        op.create_index(op.f('ix_work_experiences_candidate_id'), 'work_experiences', ['candidate_id'], unique=False)

    # 3. Educations
    if "educations" not in existing_tables:
        op.create_table(
            'educations',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('candidate_id', sa.Integer(), nullable=True),
            sa.Column('institution', sa.String(length=250), nullable=False),
            sa.Column('degree', sa.String(length=200), nullable=False),
            sa.Column('field_of_study', sa.String(length=200), nullable=False),
            sa.Column('start_year', sa.Integer(), nullable=True),
            sa.Column('end_year', sa.Integer(), nullable=True),
            sa.Column('gpa', sa.String(length=50), nullable=True),
            sa.ForeignKeyConstraint(['candidate_id'], ['candidate_identities.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_educations_id'), 'educations', ['id'], unique=False)
        op.create_index(op.f('ix_educations_candidate_id'), 'educations', ['candidate_id'], unique=False)

    # 4. Projects
    if "projects" not in existing_tables:
        op.create_table(
            'projects',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('candidate_id', sa.Integer(), nullable=True),
            sa.Column('name', sa.String(length=200), nullable=False),
            sa.Column('role', sa.String(length=150), nullable=True),
            sa.Column('technologies', sa.JSON(), nullable=True),
            sa.Column('url', sa.String(length=300), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('highlights', sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(['candidate_id'], ['candidate_identities.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_projects_id'), 'projects', ['id'], unique=False)
        op.create_index(op.f('ix_projects_candidate_id'), 'projects', ['candidate_id'], unique=False)

    # 5. Skills
    if "skills" not in existing_tables:
        op.create_table(
            'skills',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('candidate_id', sa.Integer(), nullable=True),
            sa.Column('name', sa.String(length=150), nullable=False),
            sa.Column('category', sa.String(length=100), nullable=True),
            sa.Column('years_experience', sa.Float(), nullable=True),
            sa.Column('claimable', sa.Boolean(), nullable=True),
            sa.ForeignKeyConstraint(['candidate_id'], ['candidate_identities.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_skills_id'), 'skills', ['id'], unique=False)
        op.create_index(op.f('ix_skills_candidate_id'), 'skills', ['candidate_id'], unique=False)
        op.create_index(op.f('ix_skills_name'), 'skills', ['name'], unique=False)

    # 6. Resume Versions
    if "resume_versions" not in existing_tables:
        op.create_table(
            'resume_versions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('candidate_id', sa.Integer(), nullable=True),
            sa.Column('version_name', sa.String(length=150), nullable=False),
            sa.Column('file_path', sa.String(length=500), nullable=False),
            sa.Column('content_text', sa.Text(), nullable=True),
            sa.Column('content_hash', sa.String(length=64), nullable=True),
            sa.Column('is_master', sa.Boolean(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['candidate_id'], ['candidate_identities.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_resume_versions_id'), 'resume_versions', ['id'], unique=False)
        op.create_index(op.f('ix_resume_versions_candidate_id'), 'resume_versions', ['candidate_id'], unique=False)
        op.create_index(op.f('ix_resume_versions_content_hash'), 'resume_versions', ['content_hash'], unique=False)

    # 7. Search Profiles
    if "search_profiles" not in existing_tables:
        op.create_table(
            'search_profiles',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('candidate_id', sa.Integer(), nullable=True),
            sa.Column('target_titles', sa.JSON(), nullable=True),
            sa.Column('target_locations', sa.JSON(), nullable=True),
            sa.Column('contractor_acceptable', sa.Boolean(), nullable=True),
            sa.Column('min_hours_overlap', sa.Integer(), nullable=True),
            sa.Column('min_base_salary', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['candidate_id'], ['candidate_identities.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('candidate_id')
        )
        op.create_index(op.f('ix_search_profiles_id'), 'search_profiles', ['id'], unique=False)

    # 8. Answer Bank
    if "answer_bank" not in existing_tables:
        op.create_table(
            'answer_bank',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('candidate_id', sa.Integer(), nullable=True),
            sa.Column('question_pattern', sa.String(length=300), nullable=False),
            sa.Column('answer_text', sa.Text(), nullable=False),
            sa.Column('category', sa.String(length=100), nullable=True),
            sa.Column('is_factual', sa.Boolean(), nullable=True),
            sa.Column('source', sa.String(length=100), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['candidate_id'], ['candidate_identities.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_answer_bank_id'), 'answer_bank', ['id'], unique=False)
        op.create_index(op.f('ix_answer_bank_candidate_id'), 'answer_bank', ['candidate_id'], unique=False)
        op.create_index(op.f('ix_answer_bank_question_pattern'), 'answer_bank', ['question_pattern'], unique=False)


def downgrade() -> None:
    op.drop_table('answer_bank')
    op.drop_table('search_profiles')
    op.drop_table('resume_versions')
    op.drop_table('skills')
    op.drop_table('projects')
    op.drop_table('educations')
    op.drop_table('work_experiences')
    op.drop_table('candidate_identities')
