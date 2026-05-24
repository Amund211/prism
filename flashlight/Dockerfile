FROM golang:1.26.3-alpine AS build

WORKDIR /app

COPY go.mod go.sum ./

RUN go mod download

COPY main.go ./
COPY internal/ ./internal/

# Statically linked binary; ca-certificates and tzdata come from the distroless base image.
RUN CGO_ENABLED=0 GOOS=linux go build -o /flashlight main.go

FROM gcr.io/distroless/static-debian12:nonroot@sha256:d093aa3e30dbadd3efe1310db061a14da60299baff8450a17fe0ccc514a16639

COPY --from=build /flashlight /flashlight

ENTRYPOINT ["/flashlight"]
