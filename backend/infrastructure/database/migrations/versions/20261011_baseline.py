"""Frozen current schema for fresh installations.

Revision ID: 20261011_baseline
Revises: None

Future schema changes belong in new incremental migrations;
do not regenerate this fixed baseline from the ORM.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261011_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('user',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('display_name', sa.String(length=100), nullable=True),
    sa.Column('email_verified_at', sa.DateTime(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user'))
    )
    op.create_index(op.f('ix_user_email'), 'user', ['email'], unique=True)
    op.create_table('auth_sessions',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('csrf_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_auth_sessions_user_id_user')),
    sa.PrimaryKeyConstraint('token_hash', name=op.f('pk_auth_sessions'))
    )
    op.create_index('ix_auth_sessions_user_expires', 'auth_sessions', ['user_id', 'expires_at'], unique=False)
    op.create_table('chat_session',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('mode', sa.Enum('chat', name='session_mode'), server_default='chat', nullable=False),
    sa.Column('token_used', sa.Integer(), server_default='0', nullable=False),
    sa.Column('cost', sa.Float(), server_default='0', nullable=False),
    sa.Column('status', sa.Enum('executing', 'done', 'aborted', 'error', name='session_status'), server_default='executing', nullable=False),
    sa.Column('title', sa.String(length=512), nullable=True),
    sa.Column('created_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_chat_session_user_id_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_chat_session'))
    )
    op.create_index(op.f('ix_chat_session_user_id'), 'chat_session', ['user_id'], unique=False)
    op.create_table('email_challenges',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('purpose', sa.String(length=24), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('consumed_at', sa.DateTime(), nullable=True),
    sa.Column('code_hash', sa.String(length=64), nullable=True),
    sa.Column('registration_password_hash', sa.String(length=255), nullable=True),
    sa.Column('failed_attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_email_challenges_user_id_user')),
    sa.PrimaryKeyConstraint('token_hash', name=op.f('pk_email_challenges'))
    )
    op.create_index('ix_email_challenges_user_purpose', 'email_challenges', ['user_id', 'purpose'], unique=False)
    op.create_table('file_metadata',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('owner_id', sa.BigInteger(), nullable=False),
    sa.Column('file_name', sa.String(length=255), nullable=False),
    sa.Column('storage_path', sa.String(length=512), nullable=False),
    sa.Column('file_size', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('file_type', sa.Enum('PDF', 'DOCX', 'TXT', 'MD', name='document_format'), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'PARSING', 'DONE', 'FAILED', name='parse_status'), server_default='pending', nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('metadata', sa.JSON(), nullable=True),
    sa.Column('upload_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['owner_id'], ['user.id'], name=op.f('fk_file_metadata_owner_id_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_file_metadata'))
    )
    op.create_index(op.f('ix_file_metadata_deleted_at'), 'file_metadata', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_file_metadata_owner_id'), 'file_metadata', ['owner_id'], unique=False)
    op.create_table('knowledge_bases',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('owner_id', sa.BigInteger(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('topic_tags', sa.JSON(), nullable=True),
    sa.Column('visibility', sa.Enum('PRIVATE', 'PUBLIC', name='kb_visibility'), server_default='private', nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['user.id'], name=op.f('fk_knowledge_bases_owner_id_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_knowledge_bases'))
    )
    op.create_index(op.f('ix_knowledge_bases_owner_id'), 'knowledge_bases', ['owner_id'], unique=False)
    op.create_table('chat_message',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('session_id', sa.BigInteger(), nullable=False),
    sa.Column('role', sa.Enum('user', 'assistant', 'system', name='message_role'), nullable=False),
    sa.Column('content', sa.Text(), nullable=True),
    sa.Column('refs', sa.JSON(), nullable=True),
    sa.Column('feedback', sa.String(length=8), nullable=True),
    sa.Column('created_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['chat_session.id'], name=op.f('fk_chat_message_session_id_chat_session')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_chat_message'))
    )
    op.create_index(op.f('ix_chat_message_session_id'), 'chat_message', ['session_id'], unique=False)
    op.create_table('chunk_ref',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('chunk_id', sa.String(length=128), nullable=False),
    sa.Column('file_id', sa.BigInteger(), nullable=False),
    sa.Column('source_type', sa.String(length=16), nullable=False),
    sa.Column('time_start', sa.Float(), nullable=True),
    sa.Column('time_end', sa.Float(), nullable=True),
    sa.Column('generation', sa.Integer(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['file_id'], ['file_metadata.id'], name=op.f('fk_chunk_ref_file_id_file_metadata')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_chunk_ref')),
    sa.UniqueConstraint('chunk_id', name=op.f('uq_chunk_ref_chunk_id'))
    )
    op.create_index('ix_chunk_ref_doc_generation', 'chunk_ref', ['file_id', 'generation'], unique=False)
    op.create_table('kb_documents',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('kb_id', sa.BigInteger(), nullable=False),
    sa.Column('file_id', sa.BigInteger(), nullable=False),
    sa.Column('enabled', sa.Boolean(), server_default='1', nullable=False),
    sa.Column('correction_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['file_id'], ['file_metadata.id'], name=op.f('fk_kb_documents_file_id_file_metadata')),
    sa.ForeignKeyConstraint(['kb_id'], ['knowledge_bases.id'], name=op.f('fk_kb_documents_kb_id_knowledge_bases')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_kb_documents')),
    sa.UniqueConstraint('kb_id', 'file_id', name='uq_kb_documents_kb_file')
    )
    op.create_index(op.f('ix_kb_documents_file_id'), 'kb_documents', ['file_id'], unique=False)
    op.create_index(op.f('ix_kb_documents_kb_id'), 'kb_documents', ['kb_id'], unique=False)
    op.create_table('resource_cleanup',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('owner_id', sa.BigInteger(), nullable=False),
    sa.Column('file_id', sa.BigInteger(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('target_generation', sa.Integer(), nullable=False),
    sa.Column('object_bucket', sa.String(length=128), nullable=True),
    sa.Column('object_key', sa.String(length=512), nullable=True),
    sa.Column('target_results', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='PENDING', nullable=False),
    sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('error_msg', sa.Text(), nullable=True),
    sa.Column('next_attempt_at', sa.DateTime(), nullable=False),
    sa.Column('dispatch_after', sa.DateTime(), nullable=False),
    sa.Column('lease_token', sa.String(length=36), nullable=True),
    sa.Column('lease_expires_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['file_id'], ['file_metadata.id'], name=op.f('fk_resource_cleanup_file_id_file_metadata')),
    sa.ForeignKeyConstraint(['owner_id'], ['user.id'], name=op.f('fk_resource_cleanup_owner_id_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_resource_cleanup')),
    sa.UniqueConstraint('file_id', 'kind', 'target_generation', name='uq_cleanup_file_kind_generation')
    )
    op.create_index('ix_cleanup_dispatch', 'resource_cleanup', ['status', 'next_attempt_at', 'dispatch_after'], unique=False)
    op.create_index('ix_cleanup_owner_created', 'resource_cleanup', ['owner_id', 'created_at'], unique=False)
    op.create_table('session_scopes',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('session_id', sa.BigInteger(), nullable=False),
    sa.Column('kb_id', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['kb_id'], ['knowledge_bases.id'], name=op.f('fk_session_scopes_kb_id_knowledge_bases')),
    sa.ForeignKeyConstraint(['session_id'], ['chat_session.id'], name=op.f('fk_session_scopes_session_id_chat_session')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_session_scopes')),
    sa.UniqueConstraint('session_id', 'kb_id', name='uq_session_scopes_sess_kb')
    )
    op.create_index(op.f('ix_session_scopes_kb_id'), 'session_scopes', ['kb_id'], unique=False)
    op.create_index(op.f('ix_session_scopes_session_id'), 'session_scopes', ['session_id'], unique=False)
    op.create_table('task',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('file_id', sa.BigInteger(), nullable=False),
    sa.Column('task_type', sa.String(length=24), server_default='document', nullable=False),
    sa.Column('generation', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='PENDING', nullable=False),
    sa.Column('sub_status', sa.String(length=32), server_default='QUEUED', nullable=False),
    sa.Column('progress', sa.Float(), server_default='0', nullable=False),
    sa.Column('error_msg', sa.Text(), nullable=True),
    sa.Column('failed_stage', sa.String(length=32), nullable=True),
    sa.Column('stage_metrics', sa.JSON(), nullable=True),
    sa.Column('indexing_report', sa.JSON(), nullable=True),
    sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('configuration_snapshot', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['file_id'], ['file_metadata.id'], name=op.f('fk_task_file_id_file_metadata')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_task'))
    )
    op.create_index('ix_task_doc_generation', 'task', ['file_id', 'generation'], unique=False)
    op.create_table('traces',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('session_id', sa.BigInteger(), nullable=False),
    sa.Column('message_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('steps', sa.JSON(), nullable=True),
    sa.Column('metrics', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['message_id'], ['chat_message.id'], name=op.f('fk_traces_message_id_chat_message')),
    sa.ForeignKeyConstraint(['session_id'], ['chat_session.id'], name=op.f('fk_traces_session_id_chat_session')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_traces'))
    )
    op.create_index(op.f('ix_traces_message_id'), 'traces', ['message_id'], unique=False)
    op.create_index(op.f('ix_traces_session_id'), 'traces', ['session_id'], unique=False)


def downgrade():
    op.drop_table('traces')
    op.drop_table('task')
    op.drop_table('session_scopes')
    op.drop_table('resource_cleanup')
    op.drop_table('kb_documents')
    op.drop_table('chunk_ref')
    op.drop_table('chat_message')
    op.drop_table('knowledge_bases')
    op.drop_table('file_metadata')
    op.drop_table('email_challenges')
    op.drop_table('chat_session')
    op.drop_table('auth_sessions')
    op.drop_table('user')
