FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml .
COPY uv.lock .
RUN uv pip install --system -e .

COPY orchestrator/ orchestrator/
COPY hive.json .

EXPOSE 8421

CMD ["python", "-m", "orchestrator.mcp_server"]
