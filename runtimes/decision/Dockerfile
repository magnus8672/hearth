FROM library/python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS source
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
RUN git init /laya && cd /laya && git remote add origin https://github.com/NandhaKishorM/laya.git && git fetch --depth=1 origin 8a6e1328cce2460a0e5aa348ad465bb1b5821cd2 && git checkout --detach FETCH_HEAD && test "$(git rev-parse HEAD)" = 8a6e1328cce2460a0e5aa348ad465bb1b5821cd2 && rm -rf .git
FROM library/python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/laya:/opt/app
WORKDIR /opt/app
COPY runtimes/decision/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --no-deps --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/requirements.lock
COPY --from=source /laya /opt/laya
COPY services/api/src/hearth/contracts.py /opt/app/hearth/contracts.py
COPY runtimes/decision/service.py runtimes/decision/prepare.py runtimes/decision/serve.py /opt/app/
RUN touch /opt/app/hearth/__init__.py && useradd --uid 10001 --create-home hearth
USER 10001:10001
CMD ["python", "serve.py"]
