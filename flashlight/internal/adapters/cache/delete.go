package cache

// Delete drops key, so the next GetOrCreate for it runs create() again.
// For callers that just changed the data behind an entry and must not let
// the old value be served for the rest of its ttl.
//
// It does not reach into a create() that is already running: a caller that
// claimed the key before the delete still set()s its result afterwards,
// repopulating the key with data read before the change. Deleting once the
// write is durable keeps that window to a single in-flight create.
func Delete[T any](cache Cache[T], key string) {
	cache.delete(key)
}
