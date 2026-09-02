"""Statistics layer: cluster bootstrap, share of voice, sentiment, events, verdicts.

Deterministic edges, model in nodes: every number here is computed in code
from the labels the model produced; nothing in this package calls a model.
Thresholds come from ``sonar.config`` (PRE-REGISTRATION v1.1.2 threshold
index); records are ``sonar.models``.
"""

from sonar.stats.bootstrap import Columns, Resamples, design_effect, percentile_ci, resample
from sonar.stats.compute import StatsResult, compute_stats
from sonar.stats.events import detect_events, event_days
from sonar.stats.frame import Frame, Row, build_frame, window_for
from sonar.stats.sentiment import NetStat, SentimentPlan, SourceNetStat
from sonar.stats.sov import ShareStat, SovPlan
from sonar.stats.verdict import decide_family, holm, two_sided_p

__all__ = [
    "Columns",
    "Frame",
    "NetStat",
    "Resamples",
    "Row",
    "SentimentPlan",
    "ShareStat",
    "SourceNetStat",
    "SovPlan",
    "StatsResult",
    "build_frame",
    "compute_stats",
    "decide_family",
    "design_effect",
    "detect_events",
    "event_days",
    "holm",
    "percentile_ci",
    "resample",
    "two_sided_p",
    "window_for",
]
