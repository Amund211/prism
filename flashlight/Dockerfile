FROM golang:1.26.5-alpine AS build

WORKDIR /app

COPY go.mod go.sum ./

RUN go mod download

COPY main.go ./
COPY internal/ ./internal/

# Statically linked binary; ca-certificates and tzdata come from the distroless base image.
RUN CGO_ENABLED=0 GOOS=linux go build -o /flashlight main.go

FROM gcr.io/distroless/static-debian12:nonroot@sha256:aef9602f8710ec12bde19d593fed1f76c708531bb7aba205110f1029786ead7b

COPY --from=build /flashlight /flashlight

ENTRYPOINT ["/flashlight"]
