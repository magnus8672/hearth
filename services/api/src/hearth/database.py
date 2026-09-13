from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, hide_parameters=True,
                         connect_args={"connect_timeout": 5})


@contextmanager
def scoped_session(engine: Engine, principal_id: UUID, farm_id: UUID) -> Iterator[Session]:
    with Session(engine) as session, session.begin():
        session.execute(text("SELECT set_config('hearth.principal_id', :principal, true), set_config('hearth.farm_id', :farm, true)"),
                        {"principal": str(principal_id), "farm": str(farm_id)})
        yield session


def verify_application_role(engine: Engine):
    with engine.connect() as connection:
        row = connection.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
        if row.rolsuper or row.rolbypassrls:
            raise RuntimeError("application role must not be superuser or BYPASSRLS")
        owners = connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tableowner = current_user")).all()
        if owners:
            raise RuntimeError("application role must not own application tables")
