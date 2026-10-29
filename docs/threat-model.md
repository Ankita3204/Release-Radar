# ReleaseRadar threat model (STRIDE) and where each control lives

| Threat | Control | Code | Test |
|---|---|---|---|
| Forged / tampered webhook (S, T) | HMAC-SHA256 over raw body, constant-time compare, sha256 only | `api/app/ingress/verify.py` | `tests/security/test_webhook.py` |
| Webhook replay (R) | `X-GitHub-Delivery` dedupe in Redis; idempotent upserts; alert only on transition into failure | `ingress/github_webhook.py`, `services/events.py` | `test_replay_is_deduplicated`, `test_ingest_is_idempotent_ordered_and_alerts_once` |
| Brute-force / flood on public endpoint (D) | body cap (Content-Length and streaming), bad-signature throttle | `middleware/http.py` | `test_oversized_body...`, `test_bad_signature_throttle` |
| Login CSRF, open redirect, code interception (S) | state in Redis + `__Host-` cookie, PKCE S256, fixed redirect URI and destination | `api/v1/routes/auth.py` | `test_oauth_happy_path_and_login_csrf` |
| Session theft / fixation (S, E) | opaque ids hashed in Redis, HttpOnly Secure SameSite cookie, new id per login, idle + absolute timeout | `core/security.py` | `test_logout_requires_csrf_and_kills_session` |
| CSRF on state change (T) | Origin == WEB_ORIGIN + per-session token | `core/security.py::require_csrf` | `test_csrf_and_origin_enforced` |
| Cross-tenant access / IDOR (I, E) | org from session only; tenant repositories; Postgres RLS + non-owner runtime role | `repositories/tenant.py`, `db/migrations/0001` | `tests/security/test_authz.py` |
| Stored XSS from commit/branch/workflow text (T, E) | strict field parsing, GitHub-only URLs, React text rendering, nonce CSP, ESLint ban on dangerouslySetInnerHTML | `services/events.py`, `web/src/middleware.ts` | `test_non_github_urls_are_dropped` |
| Chat-ops injection (@channel, link spoofing) | Slack escaping, Discord `allowed_mentions: none` | `services/alerts/senders.py` | `test_alert_text_cannot_ping...` |
| SSRF via alert URLs (E) | exact host/path allow-list, https only, public-IP check, no redirects, re-validated at send time | `services/alerts/ssrf.py` | `test_rejected_destinations` |
| Secret exposure at rest (I) | AES-256-GCM envelope encryption with per-row AAD and key rotation; last4 only in API | `core/crypto.py` | `test_crypto_*`, `test_csrf_and_origin_enforced` |
| Secret exposure in logs/errors (I) | redaction processor, newline neutralisation, generic 500s, validation errors don't echo input | `core/redaction.py`, `middleware/errors.py` | `test_redaction_and_log_injection` |
| Queue deserialization / abuse (E, D) | JSON-only Celery, time limits, TLS broker | `workers/celery_app.py` | (config review) |
| Prompt injection, excessive agency (T, E) | untrusted-data wrapping + redaction; fixed read-only tool allow-list with validated args | `ai/guardrails`, `ai/graph/tools.py` | `test_agent_tools_are_allow_listed_and_validated` |
| Misconfiguration (all) | fail-fast settings, prod invariants (TLS, https, secret strength) | `core/config.py`, `web/src/env.ts` | `test_config_fail_fast` |

## Known limits and residual risks (be honest in reviews)
1. **First-admin-wins installation linking.** An org installation is linked by the first org *admin* who signs in. Two admins of the same GitHub org would need a membership-invite flow; not built.
2. **DNS pinning.** SSRF protection relies on a fixed Slack/Discord host allow-list plus a resolve-time public-IP check. The connection is not pinned to the resolved IP; with fixed hosts this is low risk, but do not widen the allow-list to user-supplied hosts without adding pinning.
3. **Rate limiting is fixed-window** (burst at window edges is possible) and trusts the client IP that uvicorn derives from `--forwarded-allow-ips`. Misconfigure that flag and per-IP limits become spoofable.
4. **BFF trust.** The API trusts the `Origin` header the Next.js proxy forwards. If the API is publicly reachable (it must be, for webhooks), a non-browser attacker can set any Origin, but still needs a valid session cookie *and* its CSRF token. Consider a shared proxy secret or private networking for `/v1/*`.
5. **Not implemented:** LangGraph wiring and model calls (guardrails and tools are in place), GitHub App installation-token syncing of historical runs, org invitations, MFA enforcement (delegated to GitHub), backup/restore runbooks, and WAF/DDoS protection at the edge.
6. **Lead time for changes** is not part of the DORA output (needs commit timestamps).
