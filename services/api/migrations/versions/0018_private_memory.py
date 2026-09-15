"""Private editable memory, preserved corrections and a transactional vault outbox."""
from alembic import op

revision = '0018'
down_revision = '0017'


def upgrade():
    op.execute("""
      ALTER TABLE conversations ADD COLUMN memory_excluded boolean NOT NULL DEFAULT false;
      ALTER TABLE messages ADD COLUMN memory_revision bigint NOT NULL DEFAULT 1;
      ALTER TABLE messages ADD CONSTRAINT message_private_id UNIQUE(id,farm_id,owner_id);
      ALTER TABLE chat_runs ADD COLUMN memory_receipt jsonb NOT NULL DEFAULT '{}';
      CREATE TABLE memory_settings (
        owner_id uuid PRIMARY KEY, farm_id uuid NOT NULL, workspace_id uuid NOT NULL,
        enabled boolean NOT NULL DEFAULT true, revision bigint NOT NULL DEFAULT 1,
        generation bigint NOT NULL DEFAULT 1, projected_generation bigint NOT NULL DEFAULT 0,
        projected_at timestamptz, projection_error varchar(200),
        FOREIGN KEY(workspace_id,farm_id,owner_id) REFERENCES workspaces(id,farm_id,owner_id) ON DELETE CASCADE
      );
      CREATE TABLE memory_notes (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, owner_id uuid NOT NULL, workspace_id uuid NOT NULL,
        title varchar(200) NOT NULL, body text NOT NULL CHECK(octet_length(body)<=24000),
        kind varchar(20) NOT NULL CHECK(kind IN ('note','preference','decision')),
        enabled boolean NOT NULL DEFAULT true, revision bigint NOT NULL DEFAULT 1,
        created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
        deleted_at timestamptz, UNIQUE(id,farm_id,owner_id),
        FOREIGN KEY(workspace_id,farm_id,owner_id) REFERENCES workspaces(id,farm_id,owner_id) ON DELETE CASCADE
      );
      CREATE TABLE memory_note_revisions (
        note_id uuid NOT NULL, farm_id uuid NOT NULL, owner_id uuid NOT NULL, revision bigint NOT NULL,
        title varchar(200) NOT NULL, body text NOT NULL, kind varchar(20) NOT NULL,
        enabled boolean NOT NULL, deleted boolean NOT NULL DEFAULT false,
        origin varchar(20) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY(note_id,revision),
        FOREIGN KEY(note_id,farm_id,owner_id) REFERENCES memory_notes(id,farm_id,owner_id) ON DELETE CASCADE
      );
      CREATE TABLE memory_message_revisions (
        message_id uuid NOT NULL, farm_id uuid NOT NULL, owner_id uuid NOT NULL, revision bigint NOT NULL,
        content text NOT NULL, origin varchar(20) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY(message_id,revision),
        FOREIGN KEY(message_id,farm_id,owner_id) REFERENCES messages(id,farm_id,owner_id) ON DELETE CASCADE
      );
      CREATE INDEX memory_note_search ON memory_notes USING gin(to_tsvector('english',title || ' ' || body));
      CREATE INDEX memory_message_search ON messages USING gin(to_tsvector('english',content));
    """)
    for table in ('memory_settings', 'memory_notes', 'memory_note_revisions', 'memory_message_revisions'):
        op.execute(f"""
          ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
          ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
          CREATE POLICY private_scope ON {table}
            USING(farm_id=NULLIF(current_setting('hearth.farm_id',true),'')::uuid AND owner_id=NULLIF(current_setting('hearth.principal_id',true),'')::uuid)
            WITH CHECK(farm_id=NULLIF(current_setting('hearth.farm_id',true),'')::uuid AND owner_id=NULLIF(current_setting('hearth.principal_id',true),'')::uuid);
          GRANT SELECT,INSERT ON {table} TO hearth_app;
        """)
    op.execute("""
      GRANT UPDATE ON memory_settings,memory_notes TO hearth_app;
      CREATE FUNCTION memory_vault_dirty() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE snapshot memory_settings;
      BEGIN
        IF TG_TABLE_NAME='messages' THEN
          IF NEW.status='running' THEN RETURN NEW; END IF;
        END IF;
        INSERT INTO memory_settings(owner_id,farm_id,workspace_id)
          SELECT owner_id,farm_id,id FROM workspaces WHERE owner_id=NEW.owner_id AND farm_id=NEW.farm_id
          ON CONFLICT(owner_id) DO NOTHING;
        UPDATE memory_settings SET generation=generation+1 WHERE owner_id=NEW.owner_id AND farm_id=NEW.farm_id RETURNING * INTO snapshot;
        INSERT INTO outbox(id,farm_id,owner_id,aggregate_id,aggregate_version,event_type,payload)
          VALUES(gen_random_uuid(),snapshot.farm_id,snapshot.owner_id,snapshot.workspace_id,snapshot.generation,'memory.vault.changed','{}');
        RETURN NEW;
      END $$;
      CREATE TRIGGER memory_message_changed AFTER INSERT OR UPDATE OF content,status ON messages FOR EACH ROW EXECUTE FUNCTION memory_vault_dirty();
      CREATE TRIGGER memory_conversation_changed AFTER INSERT OR UPDATE OF title,deleted_at,memory_excluded ON conversations FOR EACH ROW EXECUTE FUNCTION memory_vault_dirty();
      CREATE TRIGGER memory_note_changed AFTER INSERT OR UPDATE ON memory_notes FOR EACH ROW EXECUTE FUNCTION memory_vault_dirty();
    """)


def downgrade():
    raise RuntimeError('Export private memory and revisions before a reviewed rollback.')
