package cache

type playerResponse struct {
	data       []byte
	statusCode int
}

type PlayerCache = Cache[playerResponse]
