# ポケモンDBの登録画面（pkdb-entry）。入口は tls-proxy の Caddy（Authentik
# forward auth）で、ここは 127.0.0.1 にだけ出す。DBへ書くのは entry.sql 系の
# 関数だけで、画面のロール pkdb_entry は表へ直接書けない。
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# root 以外で動かす（compose の read_only と合わせる）。
RUN useradd --system --uid 10001 --no-create-home entry
USER 10001:10001

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
