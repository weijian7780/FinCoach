"""FinCoach's custom retrieval-augmented generation package."""


def coach(*args, **kwargs):
    """Temporarily expose the legacy entry point without eager imports."""
    from app.legacy_rag import coach as legacy_coach

    return legacy_coach(*args, **kwargs)

__all__ = ["coach"]
