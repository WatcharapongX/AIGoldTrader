# Configuration governance

The Settings Configuration Center separates browser-owned display preferences from server authority.

- Server configuration is read-only in the web UI, comes from Pydantic Settings and environment variables, and normally requires a server restart after an operator change.
- The authenticated `GET /api/configuration/safe` endpoint is an explicit allow-list. It never serializes the Settings object or returns secrets, credential-bearing URLs, filesystem paths, account identifiers, or connection topology.
- Credential fields are represented only as `CONFIGURED`, `MISSING`, `NOT_REQUIRED`, or `NOT_EXPOSED`. Presence metadata is hidden from non-admin users.
- Trading mode, live auto trading, provider selection, broker configuration, strategy rules, and risk policy have no Settings write endpoint.
- Browser persistence is limited to locale, display timezone, density, and default chart timeframe. These are labeled local UI preferences and are never treated as trading authority.
- API failure, missing metadata, or null values remain unavailable; the client must not substitute operational defaults.
