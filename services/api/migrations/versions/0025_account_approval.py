"""Approval-only signup and explicit per-user capability grants."""
from alembic import op

revision = '0025'
down_revision = '0024'


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN access_permissions text[] NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE users ADD COLUMN created_at timestamptz NOT NULL DEFAULT now()")
    op.execute("""
      INSERT INTO permission_catalog(id) SELECT 'capability.' || id FROM capabilities ON CONFLICT DO NOTHING;
      INSERT INTO permission_catalog(id) VALUES('channel.use'),('draft.use'),('tool.use') ON CONFLICT DO NOTHING;
      -- Preserve explicitly existing Member access. Future signup receives nothing.
      UPDATE users SET access_permissions=ARRAY(SELECT id FROM permission_catalog
        WHERE id LIKE 'capability.%' OR id IN ('conversation.own','artifact.own','memory.own','api_key.own','channel.use','draft.use','tool.use'))
        WHERE EXISTS(SELECT 1 FROM role_grants g WHERE g.user_id=users.id AND g.farm_id=users.farm_id AND g.role='Member');
      CREATE OR REPLACE FUNCTION provision_member(p_farm uuid,p_issuer text,p_subject text,p_name text)
      RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
      DECLARE member_id uuid;
      BEGIN
        IF NOT EXISTS(SELECT 1 FROM public.role_grants WHERE farm_id=p_farm AND role='Owner') THEN
          RAISE EXCEPTION 'Owner setup is required';
        END IF;
        INSERT INTO public.users(id,farm_id,issuer,subject,display_name,state)
          VALUES(gen_random_uuid(),p_farm,p_issuer,p_subject,left(p_name,120),'pending')
          ON CONFLICT(issuer,subject) DO NOTHING;
        SELECT id INTO STRICT member_id FROM public.users
          WHERE farm_id=p_farm AND issuer=p_issuer AND subject=p_subject AND state IN ('pending','active');
        PERFORM set_config('hearth.principal_id',member_id::text,true);
        PERFORM set_config('hearth.farm_id',p_farm::text,true);
        INSERT INTO public.workspaces(id,farm_id,owner_id,name)
          VALUES(gen_random_uuid(),p_farm,member_id,'Personal workspace') ON CONFLICT DO NOTHING;
        RETURN member_id;
      END $$;
      CREATE FUNCTION change_member_access(p_actor uuid,p_farm uuid,p_actor_version bigint,
        p_user uuid,p_version bigint,p_state text,p_role text,p_permissions text[])
      RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
      DECLARE old_user public.users; next_version bigint;
      BEGIN
        PERFORM pg_advisory_xact_lock(hashtextextended(p_farm::text,25));
        IF NOT EXISTS(SELECT 1 FROM public.users u JOIN public.role_grants g ON g.user_id=u.id AND g.farm_id=u.farm_id
          WHERE u.id=p_actor AND u.farm_id=p_farm AND u.state='active' AND u.authorization_version=p_actor_version
          AND g.role IN ('Owner','FarmAdmin')) THEN RAISE EXCEPTION 'access_denied'; END IF;
        SELECT * INTO old_user FROM public.users WHERE id=p_user AND farm_id=p_farm FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'account_missing'; END IF;
        IF old_user.authorization_version<>p_version THEN RAISE EXCEPTION 'revision_conflict'; END IF;
        IF p_actor=p_user OR EXISTS(SELECT 1 FROM public.role_grants WHERE user_id=p_user AND farm_id=p_farm AND role='Owner')
          THEN RAISE EXCEPTION 'protected_account'; END IF;
        IF p_state NOT IN ('pending','active','suspended') OR p_role NOT IN ('Member','FarmAdmin','Operator','Auditor')
          OR p_state IS NULL OR p_role IS NULL OR p_permissions IS NULL
          OR EXISTS(SELECT 1 FROM unnest(p_permissions) AS permission WHERE permission IS NULL OR NOT EXISTS(
            SELECT 1 FROM public.permission_catalog c WHERE c.id=permission AND
            (c.id LIKE 'capability.%' OR c.id IN ('conversation.own','artifact.own','memory.own','api_key.own','channel.use','draft.use','tool.use'))))
          THEN RAISE EXCEPTION 'invalid_access'; END IF;
        IF p_state='pending' THEN p_permissions='{}'; END IF;
        UPDATE public.users SET state=p_state,access_permissions=p_permissions,authorization_version=authorization_version+1
          WHERE id=p_user RETURNING authorization_version INTO next_version;
        DELETE FROM public.role_grants WHERE user_id=p_user AND farm_id=p_farm;
        IF p_state<>'pending' THEN INSERT INTO public.role_grants(id,user_id,farm_id,role)
          VALUES(gen_random_uuid(),p_user,p_farm,p_role); END IF;
        INSERT INTO public.audit_events(id,farm_id,actor_id,action,safe_metadata) VALUES(gen_random_uuid(),p_farm,p_actor,
          'identity.access.changed',jsonb_build_object('user_id',p_user,'previous_state',old_user.state,
          'state',p_state,'role',p_role,'permissions',p_permissions,'authorization_version',next_version));
        RETURN next_version;
      END $$;
      REVOKE ALL ON FUNCTION change_member_access(uuid,uuid,bigint,uuid,bigint,text,text,text[]) FROM PUBLIC;
      GRANT EXECUTE ON FUNCTION change_member_access(uuid,uuid,bigint,uuid,bigint,text,text,text[]) TO hearth_app;
    """)


def downgrade():
    raise RuntimeError('Account approval cannot be downgraded to automatic Member grants.')
