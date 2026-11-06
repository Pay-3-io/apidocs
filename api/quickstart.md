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
# => { "success": true, "message": "...", "accessToken": "<token>", "expiresIn": 3600, "tokenType": "Bearer" }
```

Send the token as `Authorization: Bearer <accessToken>` on every subsequent call. Tokens expire after `expiresIn` seconds (one hour by default). Only the `Bearer` scheme is accepted; other schemes, or a bare token with no scheme word, return `401`. See [Authentication](authentication.md).

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

**Proving that the end user owns the email address or phone number is your responsibility.** Pay3 does not send a verification code for users registered through this API; with `PHONE` in particular, the number you pass is stored as given. Verify it in your own sign-up flow before calling `users/register`.

## 3. Run KYC

Identity verification is a prerequisite for card issuance. It runs in **your** UI using the Sumsub WebSDK; Pay3 gives you the token and starts account setup once the check is done.

### 3.1 Get a Sumsub access token (server side)

```bash
curl -X POST "$BASE_URL/kyc/access-token" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "userId": "<uuid>" }'
# => { "message": "...", "data": { "accessToken": "<sumsub token>", "userId": "<uuid>" }, "code": 0 }
```

The Sumsub token is short-lived. Expose a small endpoint on your server that calls this again, so the WebSDK can refresh it.

### 3.2 Embed the WebSDK (browser)

```html
<div id="sumsub-websdk-container"></div>
<script src="https://static.sumsub.com/idensic/static/sns-websdk-builder.js"></script>
<script>
  // Your server calls POST /kyc/access-token and returns data.accessToken.
  const getToken = () => fetch("/api/kyc-token", { method: "POST" }).then((r) => r.json()).then((j) => j.accessToken);

  let applicantId = null;

  getToken().then((token) => {
    snsWebSdk
      .init(token, getToken) // second argument: called by the SDK when the token expires
      .withConf({ lang: "en" })
      .on("idCheck.onApplicantLoaded", (payload) => {
        applicantId = payload.applicantId; // keep it: kyc/submit needs it
      })
      .on("idCheck.onApplicantStatusChanged", (payload) => {
        const done = payload.reviewStatus === "completed" &&
          payload.reviewResult && payload.reviewResult.reviewAnswer === "GREEN";
        if (done && applicantId) {
          // Your server calls POST /kyc/submit (3.3). Do it once.
          fetch("/api/kyc-submit", { method: "POST", body: JSON.stringify({ applicantId }) });
        }
      })
      .build()
      .launch("#sumsub-websdk-container");
  });
</script>
```

- `idCheck.onApplicantLoaded` gives you the `applicantId`. It belongs to the user you requested the token for; `kyc/submit` rejects an `applicantId` that does not (`400 Applicant ID does not belong to this user`).
- Submit only when `reviewStatus` is `completed` **and** `reviewAnswer` is `GREEN`. `RED` means the check failed; let the user retry in the SDK.
- In sandbox, Sumsub's test documents pass the check.

### 3.3 Submit the result (server side)

```bash
curl -X POST "$BASE_URL/kyc/submit" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "Idempotency-Key: <unique-key>" \
  -d '{ "userId": "<uuid>", "applicantId": "<sumsub-applicant-id>" }'
# => { "message": "KYC submitted successfully", "data": { "applicantId": "..." }, "code": 0 }
```

This only **starts** account and card-platform setup, asynchronously. Re-sending the same `Idempotency-Key` with the same body replays the first response; the same key with a different body returns `409`.

### 3.4 Wait for setup to finish

Do not issue a card or fund the user until setup has finished. Either:

- poll `GET /users/{userId}` until `kycStatus` is `"approved"` (see [Users](users.md); `kyc.cardIssuer.status` must be `approved` as well), or
- consume the `user.kyc.updated` webhook ([Webhooks](webhooks.md)) and act on the event whose `kycStatus` is `"approved"`.

Before that point, `card/issue_card` and `card/fetch_deposit_address` return `409 Account setup is not complete yet`, and `card/fetch_transactions` returns an empty list.

### 3.5 Fund the user, then issue

1. `POST /card/quote` with the card you intend to issue — note `data.total`.
2. `POST /pool/transfer` for at least `total` ([Partner Pool](pool.md)), and wait until `GET /pool/transfer/{transferId}` reports `settled`.
3. `POST /card/issue_card` (next section).

## 4. Issue a card

```bash
curl -X POST "$BASE_URL/card/issue_card" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "Idempotency-Key: <unique-key>" \
  -d '{ "userId": "<uuid>", "type": "virtual" }'
# => { "data": { "id": "<card id>", "cardType": "virtual", "status": "active", "last4": "1234", "program": "standard" }, "code": 0 }
```

| Field | Required | Notes |
|---|---|---|
| `userId` | yes | The registered user. |
| `type` | yes | `virtual` or `physical`. |
| `amount` | no | Must be omitted or `0`. Any other value returns `400` — fund the user with [`POST /pool/transfer`](pool.md) instead. |
| `bin` | no | BIN to issue. Defaults to the first BIN that supports the requested form factor (`537100` for virtual in sandbox). See [Endpoints](endpoints.md). |

Points to observe:

- The issuance price is managed by Pay3 and cannot be set through the API.
- Issuance requires enough user balance to cover the price. Clients that use the optional [partner pool](pool.md) top up user balances with `POST /pool/transfer`. Insufficient balance produces two distinct outcomes: `400` (refused before any card existed) and `402` (the balance ran out mid-issuance; Pay3 closes the card it had just created). Branch on `status` / `code` rather than hard-coding an amount. See [Endpoints](endpoints.md).
- `kyc/submit` only *starts* account and card setup, asynchronously. Issuing before setup completes returns `409 Account setup is not complete yet` and no card is created. Wait for the `user.kyc.updated` webhook or check `kycStatus` via `GET /users/{userId}`, then retry (this `409` does not consume the `Idempotency-Key`).
- Always send an [`Idempotency-Key`](idempotency.md) on operations that move money (card issuance, KYC submit).
- Cards belong to a [card program](endpoints.md#card-programs) (`program`: `standard` or `collateral`). Pay3 sends each card operation to the right program the same way the Pay3 app does, so you never pass it. `POST /card/balance` returns the user's balance.

Issuing with an explicit BIN:

```bash
curl -X POST "$BASE_URL/card/issue_card" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "Idempotency-Key: <unique-key>" \
  -d '{ "userId": "<uuid>", "type": "virtual", "bin": "45492418" }'
# => { "data": { "id": "...", "cardType": "virtual", "status": "active", "last4": "....", "program": "standard" }, "code": 0 }
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
#                "price": "5.00", "shipping": null, "total": "5.00" },
#      "code": 0
#    }

# Physical: pass the destination country to get the delivery fee.
curl -X POST "$BASE_URL/card/quote" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "userId": "<uuid>", "type": "physical", "bin": "45492418", "country": "JP" }'
# => { "data": { …, "price": "100.00", "shipping": "12.00", "total": "112.00" }, "code": 0 }
```

- `type` resolves to `physical` when omitted, so always pass `type` to quote a virtual card.
- A `bin` that is not in the catalog, or a `type` that BIN cannot produce, returns `400` (`Unsupported card bin/form factor`).
- `price`, `shipping`, and `total` are **strings** with two fixed decimals (`"5.00"`), not JSON numbers.
- For physical cards the delivery fee is billed **on top of** the issuance fee and paid in full by the cardholder. Charge/fund `total`, not `price`.
- `shipping` is `null` for virtual cards, when `country` is omitted, and when the carrier fee cannot be retrieved. `null` means "not available", not "free" — `total` is then `null` and `issue_card` returns `400`.
- A quote is held for **48 hours**; issuing inside that window charges exactly the quoted `total`.

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
