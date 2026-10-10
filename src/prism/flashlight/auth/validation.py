import re

# A flashlight Microsoft-tier credential
CREDENTIAL_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")

# The uuid form flashlight uses: dashed, lowercase
DASHED_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
