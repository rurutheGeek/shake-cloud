# Built on cloud-01 by `manage.py up`. Base images are pinned by digest, like
# compose.lock.yaml; update them deliberately.
FROM golang:1.27.2-trixie@sha256:e58d6f83b3416618d8bcac2b3dde1b7f7e3c4a77d25e88637f8bbae81536c48d AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
# -p=1 keeps the compiler to one package at a time. cloud-01 has little RAM and
# the default parallel build was OOM-killed there (2026-09-12).
RUN CGO_ENABLED=0 GOFLAGS=-p=1 GOMAXPROCS=1 go build -trimpath -ldflags='-s -w' -o /out/shakecloud-api ./cmd/shakecloud-api

# No shell or package manager; the health check is the binary itself.
FROM gcr.io/distroless/static-debian13:nonroot@sha256:1c2c046bc09ed40fad370b599a0b1ae7987f55b01e247cf27a7c27cd97e5bbc7
COPY --from=build /out/shakecloud-api /shakecloud-api
USER nonroot:nonroot
EXPOSE 8080
ENTRYPOINT ["/shakecloud-api"]
