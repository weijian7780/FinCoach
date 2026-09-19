"""Central config — everything is read from environment variables (.env)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _environment_flag(name: str, default: bool) -> bool:
    """Parse a conservative boolean environment flag."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# ---- Supabase (server-side) ----
# Use the SERVICE ROLE key here. It is secret and must live ONLY on this server,
# never in the mobile app.
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")

# ---- Embeddings ----
# bge-m3 -> 1024 dimensions. If you change the model, change the SQL vector(N) too.
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DIM = 1024

# ---- LLM providers (OpenAI-compatible) ----
# The optional primary provider is attempted first. The existing LLM_* provider
# remains the fallback so deployments without primary settings keep working.
LLM_PRIMARY_BASE_URL = os.environ.get("LLM_PRIMARY_BASE_URL", "")
LLM_PRIMARY_API_KEY = (
    os.environ.get("LLM_PRIMARY_API_KEY", "") or os.environ.get("GROQ_API_KEY", "")
)
LLM_PRIMARY_MODEL = os.environ.get("LLM_PRIMARY_MODEL", "")
LLM_PRIMARY_MAX_TOKENS = int(os.environ.get("LLM_PRIMARY_MAX_TOKENS", "2048"))
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")

# ---- Receipt text cleanup (Gemini; OCR text only, never the image) ----
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_RECEIPT_MODEL = os.environ.get("GEMINI_RECEIPT_MODEL", "gemini-3.1-flash-lite")

# Fetch a small candidate pool, then pass only close and relevant sources to
# the provider. This prevents overlapping or weak documents from diluting the
# grounded answer while keeping multilingual recall.
RETRIEVE_CANDIDATES = int(os.environ.get("RETRIEVE_CANDIDATES", "5"))
RETRIEVE_K = int(os.environ.get("RETRIEVE_K", "3"))
RETRIEVE_THRESHOLD = float(os.environ.get("RETRIEVE_THRESHOLD", "0.45"))
RETRIEVE_SCORE_MARGIN = float(os.environ.get("RETRIEVE_SCORE_MARGIN", "0.10"))

# ---- Web-research fallback (Tavily) ----
# Used ONLY when corpus retrieval is inadequate for a knowledge-route question.
# Corpus is always tried first. With no API key set, the fallback yields no web
# sources and the answer degrades to "insufficient evidence" rather than erroring.
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
WEB_FALLBACK_ENABLED = _environment_flag("WEB_FALLBACK_ENABLED", True)
# Trigger the web fallback when the best corpus chunk scores below this. Defaults
# to the retrieval threshold, so the fallback fires mainly on an empty corpus hit.
WEB_FALLBACK_SIM_THRESHOLD = float(
    os.environ.get("WEB_FALLBACK_SIM_THRESHOLD", "0.45")
)
WEB_FALLBACK_MAX_RESULTS = int(os.environ.get("WEB_FALLBACK_MAX_RESULTS", "4"))
WEB_FALLBACK_TIMEOUT_SECONDS = float(
    os.environ.get("WEB_FALLBACK_TIMEOUT_SECONDS", "8")
)
COACH_HISTORY_LIMIT = int(os.environ.get("COACH_HISTORY_LIMIT", "6"))
COACH_HISTORY_CHAR_LIMIT = int(
    os.environ.get("COACH_HISTORY_CHAR_LIMIT", "4000")
)
COACH_RATE_LIMIT_MINUTE = int(os.environ.get("COACH_RATE_LIMIT_MINUTE", "6"))
COACH_RATE_LIMIT_DAY = int(os.environ.get("COACH_RATE_LIMIT_DAY", "100"))
COACH_WRITE_ACTIONS_ENABLED = _environment_flag(
    "COACH_WRITE_ACTIONS_ENABLED",
    # Financial records must not be changed merely because a deployment omitted
    # this setting. Operators explicitly opt in only after action flows pass
    # their production acceptance checks.
    False,
)
COACH_PROVIDER_CONSENT_VERSION = os.environ.get(
    "COACH_PROVIDER_CONSENT_VERSION", "openrouter-free-v1"
)
LLM_TIMEOUT_SECONDS = float(os.environ.get("LLM_TIMEOUT_SECONDS", "25"))
COACH_REQUEST_DEADLINE_SECONDS = float(
    os.environ.get("COACH_REQUEST_DEADLINE_SECONDS", "30")
)
LLM_PRIMARY_TIMEOUT_SECONDS = float(
    os.environ.get("LLM_PRIMARY_TIMEOUT_SECONDS", "10")
)
LLM_FALLBACK_TIMEOUT_SECONDS = float(
    os.environ.get("LLM_FALLBACK_TIMEOUT_SECONDS", "18")
)
GROUNDING_VERIFIER_TIMEOUT_SECONDS = float(
    os.environ.get("GROUNDING_VERIFIER_TIMEOUT_SECONDS", "5")
)
GROUNDING_VERIFIER_MAX_TOKENS = int(
    os.environ.get("GROUNDING_VERIFIER_MAX_TOKENS", "256")
)
# Evidence-mode verifier budget. The legacy path keeps 256 (byte-for-byte
# rollback, invariant #9); the evidence path reads real extracted passages, which
# need more room than a snippet, so per-statement assessment uses this larger
# ceiling. Task 7 compares legacy@256 / legacy@1536 / evidence@1536 to prove the
# architecture win is not merely the token bump.
GROUNDING_VERIFIER_EVIDENCE_MAX_TOKENS = int(
    os.environ.get("GROUNDING_VERIFIER_EVIDENCE_MAX_TOKENS", "1536")
)
# Rollback flag (invariant #9): "legacy" behaves exactly as before this work;
# "evidence" enables the statement-level assessment + research pipeline. Defaults
# to legacy so adopting the new path is a deliberate, tested config flip.
COACH_GROUNDING_MODE = os.environ.get("COACH_GROUNDING_MODE", "legacy").strip().lower()
COACH_RATE_LIMIT_RETRY_MAX_SECONDS = float(
    os.environ.get("COACH_RATE_LIMIT_RETRY_MAX_SECONDS", "3")
)
# GPT-OSS uses this completion budget for both hidden reasoning and visible
# coaching text. 1024 can be consumed by high reasoning before any answer is
# returned. NVIDIA's GPT-OSS reasoning examples use 32768, which remains a
# bounded completion ceiling rather than the model's full context window.
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "32768"))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "").split(",")
    if origin.strip()
]
