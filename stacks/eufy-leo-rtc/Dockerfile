# leo_rtc クライアント本体。カメラと同じ LAN で UDP を直接話す。
# ベースイメージ・ffmpeg とも digest / sha256 を固定し、更新は明示的に行う。
FROM python:3.13-slim-bookworm@sha256:2325bb286ec344af3e5898cc224b5844e2707ac6e26b1632516fd3edc84a5e26

# Debian の ffmpeg 5.1 はパイプ入力の HEVC で参照フレームを落とし、灰色の映像に
# なる（実測: 同じ捕捉でも一括変換なら正常）。静的ビルド 7.0.2 を固定して入れる。
ARG FFMPEG_URL=https://johnvansickle.com/ffmpeg/releases/ffmpeg-7.0.2-amd64-static.tar.xz
ARG FFMPEG_SHA256=abda8d77ce8309141f83ab8edf0596834087c52467f6badf376a6a2a4c87cf67

RUN apt-get update \
    && apt-get install -y --no-install-recommends xz-utils \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -c "import urllib.request; urllib.request.urlretrieve('${FFMPEG_URL}', '/tmp/ffmpeg.tar.xz')" \
    && echo "${FFMPEG_SHA256}  /tmp/ffmpeg.tar.xz" | sha256sum -c - \
    && tar -xJf /tmp/ffmpeg.tar.xz -C /tmp \
    && install -m 0755 /tmp/ffmpeg-7.0.2-amd64-static/ffmpeg /usr/local/bin/ffmpeg \
    && rm -rf /tmp/ffmpeg*

RUN pip install --no-cache-dir cryptography==43.0.0

WORKDIR /app
COPY leo_rtc /app/leo_rtc
COPY tools /app/tools
# 状態（捕捉・鍵・スナップショット）はボリュームへ。LEO_OUT で差し替えられる。
ENTRYPOINT ["bash", "/app/tools/live_supervisor.sh"]
