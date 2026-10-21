"""Public-request attempt accounting and safe, process-local provider health."""
from dataclasses import dataclass, field
from hashlib import sha256
from threading import Lock
from time import monotonic
from typing import Callable, Any
from urllib.parse import urlsplit


def provider_identity(provider) -> str:
    parsed = urlsplit(provider.base_url)
    endpoint = f"{parsed.scheme.lower()}://{(parsed.hostname or '').lower()}"
    if parsed.port is not None:
        endpoint += f":{parsed.port}"
    endpoint += parsed.path.rstrip("/")
    # Credentials and their hashes never participate in shared health state.
    return sha256(f"{endpoint}\n{provider.model}".encode()).hexdigest()


class ProviderCooldown:
    def __init__(self, *, clock: Callable[[], float] = monotonic, ttl: float = 30):
        self.clock, self.ttl = clock, ttl
        self._states: dict[str, tuple[float, float]] = {}
        self._lock = Lock()

    def available(self, identity: str) -> bool:
        """Selection is read-only; only an actual attempt acquires a probe."""
        with self._lock:
            state = self._states.get(identity)
            now = self.clock()
            return state is None or (now >= state[0] and now >= state[1])

    def admit(self, identity: str) -> bool:
        with self._lock:
            state = self._states.get(identity)
            if state is None:
                return True
            now = self.clock()
            until, probe_until = state
            if now < until or now < probe_until:
                return False
            # Only one request may perform a half-open probe. The lease also
            # expires if a request ends before it reaches the SDK boundary.
            self._states[identity] = (until, now + 60)
            return True

    def fail(self, identity: str):
        with self._lock:
            self._states[identity] = (self.clock() + self.ttl, 0)

    def success(self, identity: str):
        with self._lock:
            self._states.pop(identity, None)


SHARED_COOLDOWN = ProviderCooldown()


def error_status(error) -> int | None:
    value = getattr(error, "status_code", None) or getattr(getattr(error, "response", None), "status_code", None)
    return value if type(value) is int else None


@dataclass
class ProviderSession:
    cooldown: ProviderCooldown = field(default_factory=lambda: SHARED_COOLDOWN)
    preferred_role: str = "primary"
    attempts: int = 0
    logical_calls: int = 0
    transient_retries: int = 0
    failed_roles: set[str] = field(default_factory=set)
    _lock: Any = field(default_factory=Lock, repr=False)

    def eligible_roles(self, providers):
        ordered = sorted(providers, key=lambda p: p.role != self.preferred_role)
        if self.preferred_role == "fallback":
            # A working fallback stays sticky; no speculative primary probe is
            # acquired by this request while it has usable work to finish.
            ordered = [p for p in ordered if p.role == "fallback"]
        return [p for p in ordered if p.role not in self.failed_roles
                and self.cooldown.available(provider_identity(p))]

    def begin_task(self):
        with self._lock:
            if self.logical_calls >= 9:
                raise RuntimeError("provider_logical_call_limit")
            self.logical_calls += 1

    def begin_attempt(self):
        with self._lock:
            if self.attempts >= 15:
                raise RuntimeError("provider_attempt_limit")
            self.attempts += 1

    def note_success(self, provider):
        self.preferred_role = provider.role
        self.failed_roles.discard(provider.role)
        self.cooldown.success(provider_identity(provider))

    def note_failure(self, provider, error):
        status = error_status(error)
        is_timeout = isinstance(error, TimeoutError) or "timeout" in type(error).__name__.lower()
        if status == 429 or (status is not None and status >= 500):
            self.cooldown.fail(provider_identity(provider))
            if provider.role == "primary":
                self.failed_roles.add(provider.role)
        elif is_timeout and provider.role == "primary":
            # Stage timeouts affect this request only, never shared health.
            self.failed_roles.add(provider.role)

    def retry_delay(self, error) -> float | None:
        if error_status(error) != 429:
            return None
        headers = getattr(getattr(error, "response", None), "headers", {}) or {}
        try:
            delay = float(headers.get("retry-after", headers.get("Retry-After", "0.5")))
        except (TypeError, ValueError):
            return None
        if not 0 <= delay <= 2:
            return None
        with self._lock:
            if self.transient_retries:
                return None
            self.transient_retries += 1
            return delay
