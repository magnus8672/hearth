import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from hearth.database import make_engine, scoped_session, verify_application_role
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


@pytest.fixture
def databases():
    app_url = os.environ.get("HEARTH_TEST_APP_DATABASE_URL")
    migration_url = os.environ.get("HEARTH_TEST_MIGRATION_DATABASE_URL")
    config = Path(".hearth/development.json")
    if not app_url and config.exists():
        values = json.loads(config.read_text())
        app_url = f"postgresql+psycopg://hearth_app:{values['HEARTH_APP_PASSWORD']}@127.0.0.1:55432/hearth"
        migration_url = f"postgresql+psycopg://hearth_migrator:{values['HEARTH_MIGRATION_PASSWORD']}@127.0.0.1:55432/hearth"
    if not app_url or not migration_url:
        if os.environ.get("HEARTH_REQUIRE_INTEGRATIONS") == "1":
            pytest.fail("Integration mode requires a real PostgreSQL application and migration URL")
        pytest.skip("Real PostgreSQL integration environment is not configured")
    app, migration = make_engine(app_url), make_engine(migration_url)
    yield app, migration
    app.dispose()
    migration.dispose()


def test_real_postgresql_role_and_private_partitions(databases):
    app, migration = databases
    verify_application_role(app)
    farm = uuid4()
    users = [uuid4(), uuid4()]
    workspaces = [uuid4(), uuid4()]
    conversations = [uuid4(), uuid4()]
    with migration.begin() as connection:
        assert int(connection.execute(text("SHOW server_version_num")).scalar_one()) >= 180000
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0020"
        connection.execute(text("INSERT INTO farms (id,name) VALUES (:id,'RLS fixture')"), {"id": farm})
        for user in users:
            connection.execute(text("INSERT INTO users (id,farm_id,issuer,subject,display_name) VALUES (:id,:farm,'fixture',:subject,'Test member')"),
                               {"id": user, "farm": farm, "subject": str(user)})
    try:
        for user, workspace, conversation in zip(users, workspaces, conversations, strict=True):
            with scoped_session(app, user, farm) as session:
                session.execute(text("INSERT INTO workspaces (id,farm_id,owner_id,name) VALUES (:id,:farm,:owner,'Private fixture')"),
                                {"id": workspace, "farm": farm, "owner": user})
                session.execute(text("INSERT INTO conversations (id,farm_id,owner_id,workspace_id,title) VALUES (:id,:farm,:owner,:workspace,'Private fixture')"),
                                {"id": conversation, "farm": farm, "owner": user, "workspace": workspace})
                session.execute(text("INSERT INTO messages (id,conversation_id,farm_id,owner_id,sequence,role,content) VALUES (:id,:conversation,:farm,:owner,1,'user','private canary')"),
                                {"id": uuid4(), "conversation": conversation, "farm": farm, "owner": user})
        with scoped_session(app, users[0], farm) as session:
            assert session.execute(text("SELECT count(*) FROM conversations")).scalar_one() == 1
            assert session.execute(text("SELECT count(*) FROM messages")).scalar_one() == 1
            assert session.execute(text("SELECT count(*) FROM conversations WHERE id=:id"), {"id": conversations[1]}).scalar_one() == 0
            assert session.execute(text("UPDATE conversations SET title='unauthorized' WHERE id=:id"), {"id": conversations[1]}).rowcount == 0
        with app.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM messages")).scalar_one() == 0
        with pytest.raises(DBAPIError), scoped_session(app, users[0], farm) as session:
            session.execute(text("INSERT INTO messages (id,conversation_id,farm_id,owner_id,sequence,role,content) VALUES (:id,:conversation,:farm,:owner,2,'user','forbidden')"),
                            {"id": uuid4(), "conversation": conversations[1], "farm": farm, "owner": users[1]})
        with pytest.raises(DBAPIError), app.begin() as connection:
            connection.execute(text("UPDATE audit_events SET action='rewritten'"))
    finally:
        for user in users:
            with scoped_session(app, user, farm) as session:
                for table in ("messages", "conversations", "workspaces"):
                    session.execute(text(f"DELETE FROM {table} WHERE farm_id=:farm"), {"farm": farm})
        with migration.begin() as connection:
            connection.execute(text("DELETE FROM users WHERE farm_id=:farm"), {"farm": farm})
            connection.execute(text("DELETE FROM farms WHERE id=:farm"), {"farm": farm})
