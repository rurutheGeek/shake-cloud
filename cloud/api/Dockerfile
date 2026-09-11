# Built on cloud-01 by `manage.py up`. Base images are pinned by digest, like
# compose.lock.yaml; update them deliberately.
FROM golang:1.27.1-trixie@sha256:9baa6b4187bbb98d240372a8a235ac0bb6b5ddd52bba1431dc2f7c0705862728 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/shakecloud-api ./cmd/shakecloud-api

# No shell or package manager; the health check is the binary itself.
FROM gcr.io/distroless/static-debian13:nonroot@sha256:1c2c046bc09ed40fad370b599a0b1ae7987f55b01e247cf27a7c27cd97e5bbc7
COPY --from=build /out/shakecloud-api /shakecloud-api
USER nonroot:nonroot
EXPOSE 8080
ENTRYPOINT ["/shakecloud-api"]
