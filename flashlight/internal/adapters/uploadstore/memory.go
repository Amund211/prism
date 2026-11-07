package uploadstore

import (
	"context"
	"crypto/md5"
	"encoding/hex"
	"fmt"
	"maps"
	"strconv"
	"sync"
	"time"

	"github.com/Amund211/flashlight/internal/app"
)

type Object struct {
	ContentType string
	Data        []byte
	generation  int64
}

type Policy struct {
	ContentType string
	Bytes       int64
	Expires     time.Time
}

// MemoryStore is for tests and local development. ClientPost stands in for
// the client's POST to the bucket.
type MemoryStore struct {
	mu           sync.Mutex
	objects      map[string]Object
	policies     map[string]Policy
	generation   int64
	failWith     error
	failDeletes  bool
	beforeCopy   func()
	beforeDelete func()
}

func NewMemoryStore() *MemoryStore {
	return &MemoryStore{objects: map[string]Object{}, policies: map[string]Policy{}}
}

func MD5Hex(data []byte) string {
	sum := md5.Sum(data)
	return hex.EncodeToString(sum[:])
}

// FailWith makes every later call return err.
func (s *MemoryStore) FailWith(err error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.failWith = err
}

// FailDeletes makes Delete fail while on is true.
func (s *MemoryStore) FailDeletes(on bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.failDeletes = on
}

// BeforeCopy runs f once, before the next Copy.
func (s *MemoryStore) BeforeCopy(f func()) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.beforeCopy = f
}

// BeforeDelete runs f once, before the next Delete.
func (s *MemoryStore) BeforeDelete(f func()) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.beforeDelete = f
}

func (s *MemoryStore) takeHook(hook *func()) {
	s.mu.Lock()
	f := *hook
	*hook = nil
	s.mu.Unlock()
	if f != nil {
		f()
	}
}

func (s *MemoryStore) SignPost(path, contentType string, size int64, expires time.Time) (app.UploadPostTarget, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.failWith != nil {
		return app.UploadPostTarget{}, s.failWith
	}
	s.policies[path] = Policy{ContentType: contentType, Bytes: size, Expires: expires}
	return app.UploadPostTarget{
		URL:    "memory://",
		Fields: map[string]string{"key": path, "Content-Type": contentType, "size": strconv.FormatInt(size, 10)},
	}, nil
}

// ClientPost stores data like a POST with target's fields would. It
// overwrites, as the bucket does.
func (s *MemoryStore) ClientPost(target app.UploadPostTarget, data []byte) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	path := target.Fields["key"]
	policy, ok := s.policies[path]
	if !ok {
		return fmt.Errorf("no policy for %s", path)
	}
	if int64(len(data)) != policy.Bytes {
		return fmt.Errorf("size %d is not %d", len(data), policy.Bytes)
	}
	s.put(path, policy.ContentType, data)
	return nil
}

func (s *MemoryStore) put(path, contentType string, data []byte) {
	s.generation++
	s.objects[path] = Object{ContentType: contentType, Data: data, generation: s.generation}
}

func (s *MemoryStore) Put(ctx context.Context, path, contentType string, data []byte) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.failWith != nil {
		return s.failWith
	}
	if _, ok := s.objects[path]; ok {
		return fmt.Errorf("%s: %w", path, app.ErrUploadObjectExists)
	}
	s.put(path, contentType, data)
	return nil
}

func (s *MemoryStore) get(path string) (Object, error) {
	if s.failWith != nil {
		return Object{}, s.failWith
	}
	obj, ok := s.objects[path]
	if !ok {
		return Object{}, fmt.Errorf("%s: %w", path, app.ErrUploadObjectNotFound)
	}
	return obj, nil
}

func (s *MemoryStore) Get(ctx context.Context, path string) ([]byte, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	obj, err := s.get(path)
	return obj.Data, err
}

func (s *MemoryStore) Stat(ctx context.Context, path string) (app.UploadObject, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	obj, err := s.get(path)
	if err != nil {
		return app.UploadObject{}, err
	}
	return app.UploadObject{Bytes: int64(len(obj.Data)), Generation: obj.generation, MD5: MD5Hex(obj.Data)}, nil
}

func (s *MemoryStore) ReadHead(ctx context.Context, path string, generation int64, n int64) ([]byte, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	obj, err := s.get(path)
	if err != nil {
		return nil, err
	}
	if obj.generation != generation {
		return nil, fmt.Errorf("%s: %w", path, app.ErrUploadObjectChanged)
	}
	return obj.Data[:min(n, int64(len(obj.Data)))], nil
}

func (s *MemoryStore) Copy(ctx context.Context, src string, generation int64, dst string) error {
	s.takeHook(&s.beforeCopy)

	s.mu.Lock()
	defer s.mu.Unlock()
	obj, err := s.get(src)
	if err != nil {
		return err
	}
	if obj.generation != generation {
		return fmt.Errorf("%s: %w", src, app.ErrUploadObjectChanged)
	}
	s.put(dst, obj.ContentType, obj.Data)
	return nil
}

func (s *MemoryStore) Delete(ctx context.Context, path string) error {
	s.takeHook(&s.beforeDelete)

	s.mu.Lock()
	defer s.mu.Unlock()
	if s.failWith != nil {
		return s.failWith
	}
	if s.failDeletes {
		return fmt.Errorf("failed to delete %s", path)
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	delete(s.objects, path)
	return nil
}

func (s *MemoryStore) Objects() map[string]Object {
	s.mu.Lock()
	defer s.mu.Unlock()
	return maps.Clone(s.objects)
}

func (s *MemoryStore) Policies() map[string]Policy {
	s.mu.Lock()
	defer s.mu.Unlock()
	return maps.Clone(s.policies)
}
