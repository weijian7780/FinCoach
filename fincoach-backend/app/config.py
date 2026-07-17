"""Central config — everything is read from environment variables (.env)."""
import os

from dotenv import load_dotenv

load_dotenv()

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

# ---- LLM (OpenAI-compatible) ----
# Leave these blank to run with a stub answer (provider decided later).
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")

# How many chunks to retrieve per question.
RETRIEVE_K = int(os.environ.get("RETRIEVE_K", "5"))
