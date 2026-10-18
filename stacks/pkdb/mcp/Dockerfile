# ポケモンDBの MCP サーバ（pkdb-mcp）。入口は tls-proxy の Caddy で、認可は
# MCP の仕様どおり OAuth（Authentik のアクセストークンをここで確かめる）。
# DBへ書くのは entry.sql 系の関数だけで、ロール pkdb_mcp は表へ直接書けない。
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pkdb_mcp ./pkdb_mcp

# root 以外で動かす（compose の read_only と合わせる）。
RUN useradd --system --uid 10001 --no-create-home mcp
USER 10001:10001

EXPOSE 8080
CMD ["uvicorn", "pkdb_mcp.server:app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
