// Package credentialrepository stores Microsoft-tier recovery credentials
// in user_credentials.
package credentialrepository

import (
	"context"
	"fmt"

	"github.com/jmoiron/sqlx"
	"github.com/lib/pq"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/trace"

	"github.com/Amund211/flashlight/internal/domain"
)

type Postgres struct {
	db     *sqlx.DB
	schema string
	tracer trace.Tracer
}

func NewPostgres(db *sqlx.DB, schema string) *Postgres {
	return &Postgres{
		db:     db,
		schema: schema,
		tracer: otel.Tracer("flashlight/credentialrepository/postgres"),
	}
}

// Insert stores a new credential. Errors never quote the hash.
func (p *Postgres) Insert(ctx context.Context, cred domain.UserCredential) error {
	ctx, span := p.tracer.Start(ctx, "Postgres.Insert")
	defer span.End()

	if len(cred.Hash) != domain.UserCredentialHashLength || cred.IdentityKey == "" || !cred.ClientType.IsKnown() || cred.CreatedAt.IsZero() || cred.ExpiresAt.IsZero() {
		return fmt.Errorf("refusing to insert an incomplete credential")
	}

	_, err := p.db.ExecContext(
		ctx,
		fmt.Sprintf(`INSERT INTO %s.user_credentials
		(credential_hash, identity_key, client_type, created_at, expires_at)
		VALUES ($1, $2, $3, $4, $5)`,
			pq.QuoteIdentifier(p.schema)),
		cred.Hash,
		cred.IdentityKey,
		string(cred.ClientType),
		cred.CreatedAt,
		cred.ExpiresAt,
	)
	if err != nil {
		return fmt.Errorf("failed to insert credential: %w", err)
	}
	return nil
}
