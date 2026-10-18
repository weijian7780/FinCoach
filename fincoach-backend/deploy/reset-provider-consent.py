"""Reset prior spending consent after introducing third-party AI disclosure.

Run once from the protected backend container. The script prints aggregate
status counts only; it never prints profile identifiers or other user data.
"""

from collections import Counter

from app.supabase_client import get_supabase


def consent_counts(client) -> Counter[str]:
    response = client.table("profiles").select("spending_records_consent").execute()
    return Counter(
        str(row.get("spending_records_consent") or "unset")
        for row in (response.data or [])
    )


client = get_supabase()
before = consent_counts(client)
client.table("profiles").update(
    {"spending_records_consent": "unset"}
).eq("spending_records_consent", "granted").execute()
after = consent_counts(client)

if after.get("granted", 0):
    raise RuntimeError("Some granted consent rows were not reset.")

print(
    {
        "reset_count": before.get("granted", 0),
        "statuses_after": dict(sorted(after.items())),
    }
)
