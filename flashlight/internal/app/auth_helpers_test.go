package app_test

import (
	"context"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
)

// Local mirrors of the production tier-agnostic tunables. Kept in
// lockstep manually: if you change a value in auth_session.go, change
// it here too. We duplicate rather than export to keep the production
// package's surface internal — these values are policy, not API.
const (
	authSessionTTL    = 1 * time.Hour
	authRefreshWindow = 2 * time.Hour
	authMaxSessionAge = 24 * time.Hour
)

const sessionIDPrefix = "flsess_"

// fakeAuthSessionRepo is a function-field stub satisfying the
// file-local repository interfaces in the app package by structural
// typing. Each test wires up only the methods it expects to be called;
// an unconfigured method will panic with a nil-pointer dereference,
// which is the signal that the use case touched a repo method the test
// didn't expect.
type fakeAuthSessionRepo struct {
	createFn             func(ctx context.Context, sess domain.AuthSession) error
	updateFn             func(ctx context.Context, id string, update func(domain.AuthSession) (domain.AuthSession, error)) (domain.AuthSession, error)
	enforceActiveIPCapFn func(ctx context.Context, identityType domain.AuthSessionIdentityType, ipHash string, maxActive int, now time.Time) error
}

func (f *fakeAuthSessionRepo) Create(ctx context.Context, sess domain.AuthSession) error {
	return f.createFn(ctx, sess)
}

func (f *fakeAuthSessionRepo) Update(
	ctx context.Context,
	id string,
	update func(domain.AuthSession) (domain.AuthSession, error),
) (domain.AuthSession, error) {
	return f.updateFn(ctx, id, update)
}

func (f *fakeAuthSessionRepo) EnforceActiveIPCap(
	ctx context.Context,
	identityType domain.AuthSessionIdentityType,
	ipHash string,
	maxActive int,
	now time.Time,
) error {
	return f.enforceActiveIPCapFn(ctx, identityType, ipHash, maxActive, now)
}
