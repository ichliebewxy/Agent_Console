# Query routing

1. If the user names a platform, inspect that platform's live registry and help.
2. If no platform is named, prefer a public/specialized source over a logged-in
   social or AI website, and state which source was selected.
3. If no adapter fits, use browser page extraction; use browser network only when
   the page's API traffic is part of the requested evidence.
4. AI websites, authenticated sites, and quota-bearing services require explicit
   user intent; do not silently spend an account quota.

For every result preserve source, query, timestamp/response status when available,
and distinguish “no results” from “adapter unavailable” and “not authenticated”.
