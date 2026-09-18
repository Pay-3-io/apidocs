# Quickstart

The shortest path through the Pay3 External (B2B) API, from registering a user to issuing a virtual card.

- **Base URL (sandbox)**: `https://api-staging.pay-3.io/functions/v1/external-service`
- Authentication uses an OAuth access token obtained with a client ID and an API key.
- The API is backend-only. You build the end-user interface yourself.

## 0. Before you start

Pay3 creates your client and invites you to the partner console. In the console's **Developer** menu:

1. Look up your **client ID** (`client_` + 32 hex characters).
2. Issue an **API key** (`pay3_sk_test_…` for sandbox, `pay3_sk_live_…` for production). The full key is shown only at issuance and is not recoverable afterwards; issue a new one if you lose it.
3. Register your **source IPs**. Only calls from registered IPs are accepted; until an IP is registered, calls from it return `403` `ip_not_registered`.

## 1. Get an access token

```bash
curl -X POST "$BASE_URL/oauth/access-token" \
  -H "Content-Type: application/json" \
  -d '{ "clientId": "client_<32 hex>", "clientSecret": "pay3_sk_test_..." }'
# => { "success": true, "accessToken": "<token>" }
```

Send the token as `Authorization: Bearer <accessToken>` on every subsequent call. Tokens expire after one hour by default. Only the `Bearer` scheme is accepted; other schemes, or a bare token with no scheme word, return `401`. See [Authentication](authentication.md).

## 2. Register a user

```bash
curl -X POST "$BASE_URL/users/register" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "signup_type": "EMAIL", "signup_type_id": "taro@example.com",
        "email": "taro@example.com", "first_name": "Taro", "last_name": "Yamada" }'
# => { "data": { "userId": "<uuid>", ... }, "code": 0 }
```

`signup_type` (`EMAIL`, `PHONE`, or `TELEGRAM`) and `signup_type_id` (the corresponding identifier) are required.

Users you register belong to your client. Other clients cannot see them.

## 3. Run KYC

Identity verification is a prerequisite for card issuance.

```bash
# Get a Sumsub access token and complete verification in your own UI
curl -X POST "$BASE_URL/kyc/access-token" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "userId": "<uuid>" }'

# After verification, submit the KYC result to start account and card setup
curl -X POST "$BASE_URL/kyc/submit" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "Idempotency-Key: <unique-key>" \
  -d '{ "userId": "<uuid>", "applicantId": "<sumsub-applicant-id>" }'
```

## 4. Issue a card

```bash
curl -X POST "$BASE_URL/card/issue_card" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "Idempotency-Key: <unique-key>" \
  -d '{ "userId": "<uuid>", "type": "virtual" }'
# => { "data": { ...card }, "code": 0 }
```

| Field | Required | Notes |
|---|---|---|
| `userId` | yes | The registered user. |
| `type` | yes | `virtual` or `physical`. |
| `amount` | no | Top-up loaded onto the user balance at issuance. Defaults to `0`. Not the issuance price. |
| `bin` | no | BIN to issue. Defaults to the first BIN that supports the requested form factor (`537100` for virtual in sandbox). See [Endpoints](endpoints.md). |

Points to observe:

- The issuance price is managed by Pay3 and cannot be set through the API.
- Issuance requires enough user balance to cover the price. Clients that use the optional [partner pool](pool.md) top up user balances with `POST /pool/transfer`. Insufficient balance produces two distinct outcomes: `400` (refused before any card existed) and `402` (the balance ran out mid-issuance; Pay3 closes the card it had just created). Branch on `status` / `code` rather than hard-coding an amount. See [Endpoints](endpoints.md).
- `kyc/submit` only *starts* account and card setup, asynchronously. Issuing before setup completes returns `409` and no card is created. Wait for the `user.kyc.updated` webhook or check `kycStatus` via `GET /users/{userId}`, then retry with a new `Idempotency-Key`.
- Always send an [`Idempotency-Key`](idempotency.md) on operations that move money (card issuance, KYC submit).

Issuing with an explicit BIN:

```bash
curl -X POST "$BASE_URL/card/issue_card" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "Idempotency-Key: <unique-key>" \
  -d '{ "userId": "<uuid>", "type": "virtual", "bin": "45492418" }'
# => { "data": { ..., "bin": "45492418" }, "code": 0 }
```

## 5. Quote a price

Quotes are informational; no funds move.

```bash
curl -X POST "$BASE_URL/card/quote" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "userId": "<uuid>", "type": "virtual", "bin": "45492418" }'
# => {
#      "message": "Quote generated",
#      "data": { "bin": "45492418", "form_factor": "virtual", "country": null, "currency": "USD",
#                "price": "5.00", "estimated_shipping": null, "total": "5.00" },
#      "code": 0
#    }
```

- `type` resolves to `physical` when omitted, so always pass `type` to quote a virtual card.
- A `bin` that is not in the catalog, or a `type` that BIN cannot produce, returns `400` (`Unsupported card bin/form factor`).
- `price`, `total`, and `estimated_shipping` are **strings** with two fixed decimals (`"5.00"`), not JSON numbers.
- `estimated_shipping` is `null` when it does not apply (virtual cards, or `country` omitted). `null` means "not applicable", not "free".

## 6. Check progress and card details

```bash
# Issuance progress events, for a loading UI
curl -X POST "$BASE_URL/card/issuance_events" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "userId": "<uuid>" }'

# Issued cards
curl -X POST "$BASE_URL/card/fetch_cards" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "userId": "<uuid>" }'
```

## 7. Receive events (optional)

To have card issuance and other events pushed to your system, configure [Webhooks](webhooks.md).

---

Next: [Authentication](authentication.md) · [Endpoints](endpoints.md) · [Webhooks](webhooks.md) · [openapi.yaml](openapi.yaml)
