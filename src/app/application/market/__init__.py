"""Market/news application layer (issue #1): persisting fetched news and its
per-article `analysis_status`, so it survives across requests instead of being
recomputed from scratch on every `GET /api/v1/news` call.
"""
