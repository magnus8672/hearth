"""Audience-bound sessions and atomic personal account provisioning.

Revision ID: 0002
"""
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade():
    op.execute("""
        CREATE TABLE login_attempts (
          state_hash text PRIMARY KEY, audience text NOT NULL CHECK (audience IN ('admin','user')),
          browser_hash text NOT NULL, payload text NOT NULL,
          expires_at timestamptz NOT NULL DEFAULT now() + interval '5 minutes');
        CREATE TABLE browser_sessions (
          token_hash text PRIMARY KEY, audience text NOT NULL CHECK (audience IN ('admin','user')),
          user_id uuid NOT NULL, farm_id uuid NOT NULL, csrf_token text NOT NULL,
          credentials text NOT NULL, authorization_version bigint NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          last_seen_at timestamptz NOT NULL DEFAULT now(),
          expires_at timestamptz NOT NULL DEFAULT now() + interval '8 hours',
          FOREIGN KEY (user_id,farm_id) REFERENCES users(id,farm_id));
        CREATE INDEX browser_sessions_user ON browser_sessions(user_id);
        GRANT SELECT,INSERT,UPDATE,DELETE ON login_attempts,browser_sessions TO hearth_app;
        CREATE UNIQUE INDEX personal_workspace ON workspaces(farm_id,owner_id);
    """)
    # This narrowly scoped function can create Member accounts, never privileged grants.
    # Ownership stays with the migration role; search_path cannot be caller-controlled.
    op.execute("""
        CREATE FUNCTION provision_member(p_farm uuid, p_issuer text, p_subject text, p_name text)
        RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        DECLARE member_id uuid;
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM public.role_grants WHERE farm_id=p_farm AND role='Owner') THEN
            RAISE EXCEPTION 'Owner setup is required';
          END IF;
          INSERT INTO public.users(id,farm_id,issuer,subject,display_name)
            VALUES(gen_random_uuid(),p_farm,p_issuer,p_subject,left(p_name,120))
            ON CONFLICT (issuer,subject) DO NOTHING;
          SELECT id INTO STRICT member_id FROM public.users
            WHERE farm_id=p_farm AND issuer=p_issuer AND subject=p_subject AND state='active';
          INSERT INTO public.role_grants(id,user_id,farm_id,role)
            VALUES(gen_random_uuid(),member_id,p_farm,'Member') ON CONFLICT DO NOTHING;
          PERFORM set_config('hearth.principal_id',member_id::text,true);
          PERFORM set_config('hearth.farm_id',p_farm::text,true);
          INSERT INTO public.workspaces(id,farm_id,owner_id,name)
            VALUES(gen_random_uuid(),p_farm,member_id,'Personal workspace') ON CONFLICT DO NOTHING;
          RETURN member_id;
        END $$;
        REVOKE ALL ON FUNCTION provision_member(uuid,text,text,text) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION provision_member(uuid,text,text,text) TO hearth_app;
    """)


def downgrade():
    op.execute("DROP FUNCTION provision_member(uuid,text,text,text)")
    op.execute("DROP INDEX personal_workspace")
    op.execute("DROP TABLE browser_sessions,login_attempts")
