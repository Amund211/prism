from prism import VERSION_STRING

# Client identification headers sent with every request to the flashlight
# backend so requests/metrics/logs can be sliced by client type and version.
#
# NOTE: These headers must ONLY be sent to flashlight - never to Hypixel,
#       Mojang, or any other third-party server. Do not add them to the shared
#       requests session (which is also used for the Hypixel API); merge them
#       into the per-request headers of flashlight calls instead.
CLIENT_TYPE = "prism"


def make_flashlight_client_headers() -> dict[str, str]:
    """Return the client identification headers for requests to flashlight"""
    return {
        "X-Client-Type": CLIENT_TYPE,
        "X-Client-Version": VERSION_STRING,
    }
