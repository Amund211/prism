from prism.player import MISSING_WINSTREAKS, Winstreaks


class PlaceholderWinstreakProvider:
    @property
    def seconds_until_unblocked(self) -> float:
        """Return the number of seconds until we are unblocked"""
        return 0

    def get_estimated_winstreaks_for_uuid(
        self, uuid: str, *, antisniper_api_key: str
    ) -> tuple[Winstreaks, bool]:
        return MISSING_WINSTREAKS, False
