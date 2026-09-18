# Authentication

Every Pay3 External API call is authenticated with a short-lived OAuth access token obtained from your client credentials.

## Credentials

Clients are created by Pay3. Your credentials (API keys), your webhook endpoint, and your source-IP allowlist are all managed in the **Developer** menu of the partner console.

| Value | Format | Where it comes from |
|---|---|---|
| `clientId` | `client_` + 32 hex characters | Shown in the Developer menu. |
| `clientSecret` | API key: `pay3_sk_test_…` (sandbox) or `pay3_sk_live_…` (production) | Issued in the Developer menu. The full key is displayed only at the moment of issuance and is not stored in plaintext by Pay3 — issue a new key if you lose it. |

## Requesting an access token

```bash
curl -X POST "$BASE_URL/oauth/access-token" \
  -H "Content-Type: application/json" \
  -d '{ "clientId": "client_<32 hex>", "clientSecret": "pay3_sk_test_..." }'
# => { "success": true, "accessToken": "<token>" }
```

This endpoint accepts `POST` only. Other methods return `404 { "message": "Unknown endpoint. Check the HTTP method and path against docs/api.", "code": 404 }`. The method check runs before authentication, so a wrong method never looks like a credentials problem.

## Using the token

- Send the token as `Authorization: Bearer <accessToken>`.
- Only the `Bearer` scheme is accepted. The scheme word is case-insensitive, so `bearer` also works. Any other scheme word, or a bare token with no scheme word, returns `401 { "message": "Unauthorized", "code": 401 }`.
- The header value must be exactly two words separated by a single space. A double space, a tab, or extra words after the token return `401` even when the token itself is valid, so build the value as `"Bearer " + accessToken.trim()`. Trailing whitespace is stripped by HTTP itself and does not cause a `401`.
- Tokens expire after one hour by default. Request a new one after expiry.
- The token carries only a client identifier, an issue time, and an expiry. Its format is an implementation detail and can change without notice, so do not decode it or depend on its contents.

## Errors

Errors from this endpoint use the same two-key shape as the rest of the API: `{ message, code }`.

| Status | Body | Meaning |
|---|---|---|
| `400` | `{ "message": "Invalid JSON body", "code": 400 }` | The body could not be parsed as JSON. Input errors are never reported as `500`. |
| `400` | `{ "message": "Client ID or name is required", "code": 400 }` | `clientId` was absent. |
| `401` | `{ "message": "Invalid client credentials", "code": 401 }` | The `clientId` / `clientSecret` pair was not accepted. |
| `500` | `{ "message": "Failed to resolve client", "code": 500 }` or `{ "message": "Failed to issue access token", "code": 500 }` | A Pay3-side fault. Retry the request unchanged. |

An unknown `clientId` and a mismatched `clientSecret` return the same `401`. When troubleshooting, check both values: `clientId` must be the client ID (`client_…`), not a display name, and the API key prefix (`test` / `live`) must match the environment you are calling.

## Tenant isolation

- Users you create through `users/register` are bound to your client.
- Every data operation is scoped to your client boundary. Users and cards belonging to other clients are not reachable and return `404` even when they exist.
- Clients are mutually invisible.

## Handling credentials

- Keep API keys and access tokens server-side. Do not expose them in a frontend or in logs.
- To rotate a key, issue a new one in the Developer menu, switch your systems over, then revoke the old one. You can hold several named keys at once, so rotation needs no downtime.
