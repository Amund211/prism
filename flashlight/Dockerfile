FROM golang:1.27.3-alpine@sha256:b8c9b82affbbb82a020bbcf998dad2ba9516944ac7e883524642a481a9505e9c AS build

WORKDIR /app

COPY go.mod go.sum ./

RUN go mod download

COPY main.go ./
COPY internal/ ./internal/

# Statically linked binary; ca-certificates and tzdata come from the distroless base image.
RUN CGO_ENABLED=0 GOOS=linux go build -o /flashlight main.go

FROM gcr.io/distroless/static-debian12:nonroot@sha256:afa5c872c891853ca7fcf1f12c3edb23f7eeef36189728842dd51042ff57f7ab

COPY --from=build /flashlight /flashlight

ENTRYPOINT ["/flashlight"]
