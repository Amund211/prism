package playerprovider

import (
	"context"
	"fmt"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

type hypixelPlayerProvider struct {
	hypixelAPI HypixelAPI

	metrics hypixelPlayerProviderMetricsCollection
}

func NewHypixelPlayerProvider(hypixelAPI HypixelAPI) (PlayerProvider, error) {
	meter := otel.Meter("playerprovider/hypixel_provider")
	metrics, err := setupHypixelPlayerProviderMetrics(meter)
	if err != nil {
		return nil, fmt.Errorf("failed to set up metrics: %w", err)
	}

	return &hypixelPlayerProvider{
		hypixelAPI: hypixelAPI,

		metrics: metrics,
	}, nil
}

func (h *hypixelPlayerProvider) GetPlayer(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
	if !strutils.UUIDIsNormalized(uuid) {
		logging.FromContext(ctx).Error("UUID is not normalized", "uuid", uuid)
		err := fmt.Errorf("UUID is not normalized")
		reporting.Report(ctx, err, map[string]string{
			"uuid": uuid,
		})
		return nil, err
	}

	playerData, statusCode, queriedAt, err := h.hypixelAPI.GetPlayerData(ctx, uuid)
	if err != nil {
		// NOTE: HypixelAPI implementations handle their own error reporting
		return nil, fmt.Errorf("failed to get player data: %w", err)
	}

	player, err := HypixelAPIResponseToPlayerPIT(ctx, uuid, queriedAt, playerData, statusCode)
	if err != nil {
		// NOTE: HypixelAPIResponseToPlayerPIT handles its own error reporting
		return nil, fmt.Errorf("failed to convert hypixel api response to player: %w", err)
	}

	h.metrics.requestCount.Add(ctx, 1, metric.WithAttributes(attribute.Bool("got_player", player != nil)))

	return player, nil
}

type hypixelPlayerProviderMetricsCollection struct {
	requestCount metric.Int64Counter
}

func setupHypixelPlayerProviderMetrics(meter metric.Meter) (hypixelPlayerProviderMetricsCollection, error) {
	requestCount, err := meter.Int64Counter("playerprovider/hypixel_provider/returned_players")
	if err != nil {
		return hypixelPlayerProviderMetricsCollection{}, fmt.Errorf("failed to create metric: %w", err)
	}

	return hypixelPlayerProviderMetricsCollection{
		requestCount: requestCount,
	}, nil
}
