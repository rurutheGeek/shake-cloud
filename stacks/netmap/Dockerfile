# ネットワーク図。Flint 3 の設定は SSH（netmap-dump しか実行できない鍵）で読むので ssh を入れる。
FROM python:3.13-slim@sha256:57b29a7c050c4e679e4bea572e14b3965cf4b5839de2da49d55e49ffc4024f39

RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-client \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 netmap

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

USER netmap
EXPOSE 8096
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8096", "--proxy-headers"]
