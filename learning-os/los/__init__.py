"""AI Learning OS — importable package root.

The on-disk monorepo dir is ``learning-os/`` (hyphenated, not importable); this package is ``los``.
Phase 0 provides the event substrate (``los.events``), shared domain primitives
(``los.domain_shared``), and the first two services (``los.services.gateway`` / ``.ingestion``).
"""

__all__ = ["__version__"]
__version__ = "0.0.0"
