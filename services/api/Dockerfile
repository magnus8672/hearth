FROM library/rust:1.96.1-slim-bookworm@sha256:e18a79fc84dfcfc3ab5ba72290398a644c135c97eaa881447fddc354ee4701a3 AS rust-toolchain
FROM library/python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS build
COPY --from=rust-toolchain /usr/local/cargo /usr/local/cargo
COPY --from=rust-toolchain /usr/local/rustup /usr/local/rustup
ENV CARGO_HOME=/usr/local/cargo RUSTUP_HOME=/usr/local/rustup PATH=/usr/local/cargo/bin:$PATH
ENV CARGO_BUILD_JOBS=2 RUSTFLAGS="-C target-cpu=x86-64-v2"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /opt/hearth
RUN apt-get update && apt-get install -y --no-install-recommends build-essential pkg-config cmake && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.12.5
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-binary-package nemo-switchyard
COPY services/api services/api
COPY alembic.ini ./
RUN uv sync --locked --no-dev --no-binary-package nemo-switchyard

FROM build AS test
RUN uv sync --locked --group knowledge --no-binary-package nemo-switchyard

FROM library/python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/hearth
COPY --from=build /opt/hearth /opt/hearth
RUN useradd --uid 10001 --create-home hearth
USER 10001:10001
EXPOSE 8080
CMD [".venv/bin/uvicorn", "hearth.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
