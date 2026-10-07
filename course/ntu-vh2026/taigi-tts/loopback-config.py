"""Parse explicit local HTTP origins and ports for classroom sidecars."""
import os
from urllib.parse import urlsplit


def configuration(prefix='AIRI_TAIGI', default_port=8883):
    port = int(os.environ.get(prefix + '_PORT', str(default_port)))
    if not 1 <= port <= 65535:
        raise ValueError('Sidecar port must be between 1 and 65535')
    origins = os.environ.get(prefix + '_ALLOWED_ORIGINS',
        'http://127.0.0.1:5174,http://localhost:5174').split(',')
    validated = []
    for origin in origins:
        origin = origin.strip()
        parsed = urlsplit(origin)
        if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
                or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment
                or parsed.port is not None and not 1 <= parsed.port <= 65535):
            raise ValueError('Allowed origins must be exact loopback HTTP origins, without paths')
        if origin not in validated:
            validated.append(origin)
    return port, validated
