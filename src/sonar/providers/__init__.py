"""Provider adapters for Monid endpoints.

Importing this package registers every adapter into
:data:`sonar.providers.registry.PROVIDERS`, so registration never depends
on which module a caller happened to import first.
"""

from sonar.providers import elevenlabs as _elevenlabs  # noqa: F401
from sonar.providers import facebook as _facebook  # noqa: F401
from sonar.providers import g2 as _g2  # noqa: F401
from sonar.providers import google_maps as _google_maps  # noqa: F401
from sonar.providers import instagram as _instagram  # noqa: F401
from sonar.providers import news as _news  # noqa: F401
from sonar.providers import reddit as _reddit  # noqa: F401
from sonar.providers import tiktok as _tiktok  # noqa: F401
from sonar.providers import trustpilot as _trustpilot  # noqa: F401
from sonar.providers import x as _x  # noqa: F401
from sonar.providers import youtube as _youtube  # noqa: F401
from sonar.providers import youtube_comments as _youtube_comments  # noqa: F401
