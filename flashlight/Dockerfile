FROM golang:1.25 AS build

WORKDIR /app

COPY go.mod go.sum ./

RUN go mod download

COPY main.go ./
COPY internal/ ./internal/

# Disable cgo and use the builtin network stack to get a statically linked binary
# https://blog.wollomatic.de/posts/2025-01-28-go-tls-certificates/
RUN CGO_ENABLED=0 GOOS=linux go build -tags=netgo -o /flashlight main.go

FROM scratch

COPY --from=build /flashlight /flashlight

USER 1001:1001

ENTRYPOINT ["/flashlight"]
