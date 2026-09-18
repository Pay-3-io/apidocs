# Endpoints

Every data-plane endpoint of the Pay3 External API.

All requests require `Authorization: Bearer <accessToken>`. Successful responses have the shape `{ message, data, code }` with `code: 0`; errors return `{ message, code }` with the matching HTTP status.

| Environment | Base URL |
|---|---|
| Sandbox | `https://api-staging.pay-3.io/functions/v1/external-service` |
| Production | `https://api.pay-3.io/functions/v1/external-service` |

The base URL includes the trailing `/external-service`. Every path below sits directly under it.

## Users

### POST /users/register

Creates a user and attributes it to your client.

| Field | Required | Notes |
|---|---|---|
| `signup_type` | yes | `"EMAIL"` \| `"PHONE"` \| `"TELEGRAM"` |
| `signup_type_id` | yes | The identifier matching `signup_type`: an email address, a phone number, or a Telegram id |
| `first_name` | yes | |
| `last_name` | no | |
| `email`, `phone_number`, `telegram_id` | no | |
| `referral_code` | no | See [Referral Codes](referral-codes.md) |

```json
{ "signup_type": "EMAIL", "signup_type_id": "taro@example.com", "email": "taro@example.com", "first_name": "Taro" }
```

- 200: `{ data: { userId, first_name, last_name, card_issued, referralCode }, code: 0 }` — `referralCode` is the code the user is attributed to, or `null`.
- **Idempotent, no `Idempotency-Key` needed.** Re-sending the same `(signup_type, signup_type_id)` returns `200` with the **same `userId`**; no duplicate person is created. This holds for `EMAIL`, `PHONE` and `TELEGRAM` alike, and users who signed up through a `?ref=` link resolve into the same set ([Users](users.md)).
- Identity matching is a **byte-for-byte** comparison of `signup_type_id`. No normalisation is applied, so send EMAIL in lower case and PHONE in E.164.
- 400: the request is malformed and **no user is created**. Input errors are never reported as `500`.

  | Cause | Body |
  |---|---|
  | Body is not parseable JSON (empty body, trailing comma, missing brace) | `{ "message": "Invalid JSON body", "code": 400 }` |
  | `signup_type` is not `EMAIL` / `PHONE` / `TELEGRAM` | `{ "message": "Unsupported signup_type", "code": 400 }` |
  | `signup_type_id` missing or empty | `{ "message": "User data missing", "code": 400 }` |
  | `referral_code` malformed, or not issued by your client | `{ "message": "referral_code is unknown or disabled", "code": 400 }` |

- 409: the `signup_type_id` already belongs to a user **outside your client** (`{ "message": "This signup_type_id is already registered outside your account", "code": 409 }`). The body carries `message` and `code` only — no `userId`, no name. Retrying does not change the outcome.

### GET /users?id=&lt;userId&gt;

Returns user information, scoped to your own tenant.

- 200: `{ data: { id, first_name, last_name, email, phone_number, telegram_id, client_id, created_at, updated_at, signup_type_id, signup_type, card_issued, kyc_verified }, code: 0 }` — exactly these 13 fields; no internal identifiers are included.

For partner user status use `GET /users/{userId}` instead ([Users](users.md)).

## KYC

### POST /kyc/access-token

Issues a Sumsub access token so you can run the identity verification flow in your own UI.

- body: `{ userId }`
- 200: `{ data: { accessToken, userId }, code: 0 }`

### POST /kyc/submit

Call this after identity verification completes to start account and card-platform setup. **Idempotent** — an [Idempotency-Key](idempotency.md) is recommended.

- headers: `Idempotency-Key: <unique>`
- body: `{ userId, applicantId }`
- 200: `{ data: { applicantId }, code: 0 }`

Setup runs asynchronously; this call only starts it.

## Card

### POST /card/application/start

Starts the card application.

- body: `{ userId }`

### POST /card/application

Returns the state of the card application.

- body: `{ userId }`

### POST /card/quote

Prices an issuance before you commit to it. **No funds move** — the call is purely informational.

- body: `{ userId, type?, bin?, country? }`
  - `type` (default `"physical"`): `"virtual"` \| `"physical"`. Always pass it explicitly to quote a virtual card.
  - `bin` (optional): see [Card BINs](#card-bins). Omitted, the first BIN that supports the requested form factor is used.
  - `country` (optional): destination. For `physical`, returns the shipping estimate above the baseline.
- 200: `{ data: { bin, form_factor, country, currency, price, estimated_shipping, total }, code: 0 }`
  - `total` is the price actually charged at issuance.
  - `price`, `total` and `estimated_shipping` are **fixed 2-decimal strings** (`"5.00"`), like every other money field.
  - `estimated_shipping` is `null` when it does not apply (virtual cards, or `country` omitted). **`null` means "not applicable", not "free".**

```json
{ "bin": "45492418", "form_factor": "virtual", "country": null, "currency": "USD", "price": "5.00", "estimated_shipping": null, "total": "5.00" }
```

- 400: unsupported `bin` / `type` combination (`{ "message": "Unsupported card bin/form factor: <bin>/<form factor>", "code": 400 }`).

### POST /card/issue_card

Issues a card. **Idempotent** — an [Idempotency-Key](idempotency.md) is strongly recommended. KYC must be complete.

- headers: `Idempotency-Key: <unique>`
- body: `{ userId, type, amount?, bin? }`
  - `type`: `"virtual"` \| `"physical"`
  - `amount` (default 0): top-up loaded onto the user balance at issuance. **This is not the issuance price** — pricing is managed by Pay3.
  - `bin` (optional): omitted, the first BIN that supports the form factor is used (`537100` for virtual in sandbox).
- 200: `{ data: { id, cardType, status, last4 }, code: 0 }`
  - `id`: card ID, the same value as `cardId` in the `card.issued` webhook ([Webhooks](webhooks.md)).
  - `cardType`: `"virtual"` \| `"physical"`; `status`: `"active"` \| `"issued"` \| `"shipped"` \| `"activated"` \| `"frozen"`.
  - `last4`: last four digits of the card number. **PAN, CVV, expiry, billing address and email are never returned.**
  - These four fields are the entire response; the card platform's raw payload is not passed through.
- 400: `bin` unknown, disabled, or not allowed for that form factor. **A user balance below the issuance price also returns this 400** — see below.
- 402: the balance ran out mid-issuance — see below.
- 403: **two distinct cases; branch on `message`** (both carry `code: 403`).

  | message | Meaning | What to do |
  |---|---|---|
  | `This card is not available for your account` | The `bin` is not permitted for this account | Retry with a permitted `bin` |
  | `Card limit reached for your account` / `Card limit reached for this card type` | The **card count limit** has been reached | Review the user's existing cards; contact Pay3 if the limit needs raising |

  The default limit is 1 virtual and 1 physical card per user, but it is a configurable safety limit that may differ per client. **Do not hard-code the count — branch on the 403 `message`.** Changing the `bin` does not clear a limit error.
- 409: issuance finished without producing a card (`{ "message": "Card issuance did not complete: no card was created. ...", "code": 409 }`). Almost always this means the account and card-platform setup has not finished yet: `kyc/submit` starts that setup asynchronously, so calling issuance too early lands in this window. **No card is created and no `card.issued` webhook is sent.** Confirm setup has completed (`GET /users/{userId}` → `kycStatus` / `cards`, or the `user.kyc.updated` webhook) and retry with a **new `Idempotency-Key`**.

#### Insufficient balance: 400 and 402 are two different cases

Neither leaves a card behind, but they stop at different points. Branch on `status` (and `code`).

| Status | Meaning | What happened | Body |
|---|---|---|---|
| **400** | Balance below the issuance price (pre-flight rejection) | Refused **before** issuance started. **No card was created** | `{ "message": "Not enough balance to issue card", "code": 400 }` |
| **402** | Collection failed mid-issuance | The card was created, the price could not be collected, and Pay3 voided that card. `card_issued` stays false | `{ "message": "Not enough balance to issue card. The issuance was rolled back and no card was created.", "code": 402 }` |

- The remedy is the same in both cases: top up, then retry with a **new `Idempotency-Key`**. Re-sending the same key replays the first response ([Idempotency](idempotency.md)).
- **Do not hard-code the required amount — branch on `status` / `code`.** The amount deducted at issuance is Pay3-side configuration and differs between sandbox and production. Checking only `if (status === 402)` misses the most common insufficient-balance case, which is **400**.

### Card BINs

Accepted `bin` values come from the Pay3 card BIN catalog, which is fail-closed: a value outside the catalog is rejected for both issuance and quoting. Sandbox values:

| BIN | Brand / name | Form factor |
|---|---|---|
| `537100` | Mastercard / Virtual Card | virtual (default when `bin` is omitted) |
| `45492418` | Visa / Pay3 Card | virtual |
| `49387519` | Visa / White Card | physical |

Each BIN supports specific form factors, so a `bin` / `type` combination the catalog does not allow returns 400 (never 500). Production values are provided separately.

### POST /card/issuance_events

Returns issuance progress events, for driving a loading or status UI.

- body: `{ userId, applicationId?, since? }` (`since` is an ISO timestamp)
- 200: `{ data: { events: [{ phase, meta, created_at, application_id }] }, code: 0 }`
- `phase`: `validating → provider_call → db_committed → card_fetched → funds_settled → shipping_requested → done`, or `failed`.

### POST /card/fetch_cards

Lists a user's cards.

- body: `{ userId }`
- 200: `{ data: [{ id, cardType, status, last4, currency, balance }], code: 0 }`
  - `balance` is a **fixed 2-decimal string** (`"2.60"`). When it cannot be retrieved it is `null` — never rounded to `"0.00"`, so a zero balance stays distinguishable from a missing one.
  - `currency` is an ISO currency code (for example `"USD"`); `last4` is the last four digits of the card number.
  - These six fields are the entire response. Card-platform internal identifiers, billing address, email, price lists and feature flags are not included.
  - Card type, status and last four digits are also available per user from `cards` in `GET /users/{userId}` ([Users](users.md)).

### POST /card/fetch_card_details

- body: `{ userId, cardId }`
- **Card number, CVV and expiry never cross the partner boundary.** This surface requires a two-factor step-up credential, which tokens issued through the partner OAuth flow do not carry, so partner integrations receive **`401`** here. On `200`, `data` is empty.
- For card type, status and last four digits use `POST /card/fetch_cards` or `GET /users/{userId}`.

### POST /card/fetch_deposit_address

Returns a crypto deposit address.

- body: `{ userId, token, network }`
- Accepted token and network combinations are listed in [openapi.yaml](openapi.yaml).

### POST /card/set_card_pin

Sets the ATM PIN.

- body: `{ userId, cardId, pin }`

### POST /card/lock_card and POST /card/unlock_card

Locks or unlocks a card.

- body: `{ userId, cardId }`

### POST /card/fetch_transactions

Returns transaction history.

- body: `{ userId, page, limit }`

## Partner Pool

Tops up user balances from a pool deposit: balance, transfer instructions and ledger. → **[Partner Pool](pool.md)**

- `GET /pool/balance` / `GET /pool/deposit_address`
- `POST /pool/transfer` (`Idempotency-Key` required)
- `GET /pool/transfer/{transferId}` / `GET /pool/transfers` (`status` / `userId` / `from` / `to` / `limit` / `offset`)
- `GET /pool/ledger` (`type` / `from` / `to` / `limit` / `offset`)

The list endpoints (`/pool/transfers`, `/pool/ledger`, `/users/list`, `GET /referral-codes`) accept **a fixed set of parameter names and reject anything else with 400**, so a misspelling never comes back as an unfiltered `200` (see [Query parameter validation](pool.md#query-parameter-validation)).

`from` and `to` filter on `createdAt`. **A date-only value is interpreted in UTC and `to` covers the whole day**, so a single day is `?from=2026-09-15&to=2026-09-15` (see [Date boundaries](pool.md#date-boundaries)).

## Referral Codes

Register, enable, disable and delete referral codes, and attribute users to them. → **[Referral Codes](referral-codes.md)**

- `GET /referral-codes` / `POST /referral-codes`
- `PATCH /referral-codes/{code}` / `DELETE /referral-codes/{code}`

`POST /users/register` accepts a `referral_code`.

## User Status

List your users and read their KYC and card issuance status. → **[Users](users.md)**

- `GET /users/list` (scope `users:status`; accepts only `limit` 1–200 and `offset`)
- `GET /users/{userId}` (scope `users:status`; unattributed and non-existent ids both return 404)

The set of users returned by the list, accepted by the lookup, and accepted by `POST /pool/transfer` is **identical**.

`referralCode` from `GET /users/list` and `partnerRefCode` from the `user.registered` webhook are **the same value** — the referral code fixed at that user's sign-up. The two spellings are per-channel; the values match directly.

## Credentials, webhooks and source IPs

API key issuance and revocation, the webhook endpoint and signing key, and the source-IP allowlist are all managed in the **Developer menu of the partner console**.

Secrets — API keys and signing keys — are shown in clear text only once, at the moment of issuance; if you lose a copy, re-issue it in the console.

## Unknown paths and error bodies

Unrecognised paths and unsupported HTTP methods return a **JSON 404**. This holds for `/pool/*`, `/referral-codes*`, `/users/*` and `/oauth/*`.

`/kyc/*` and `/card/*` resolve the `userId` in the body before routing on the path, so what an unknown sub-path or unsupported method returns there depends on the body you sent:

| Body sent | Response from `/card/<unknown>` or `/kyc/<unknown>` |
|---|---|
| Valid JSON with a `userId` attributed to you | `404 {"message":"Unknown endpoint. …","code":404}` |
| Valid JSON with an unknown `userId` | `404 {"message":"User not found","code":-1}` (`code` does not match the HTTP status) |
| Valid JSON with no `userId` | `400 {"message":"User ID is required","code":400}` |
| Not parseable as JSON, or no body | `400 {"message":"Invalid JSON body","code":400}` |

On these two subtrees a misspelled path is therefore not always reported as a path error, so use the paths exactly as documented.

The unparseable-body outcome is uniform across every subtree: broken JSON, an empty body, or a body that is not a JSON object (`null`, a string, a number, an array) returns **`400 {"message":"Invalid JSON body","code":400}`**. There is no `text/plain` `500` — input errors are never reported as `500` ([Authentication](authentication.md)).

→ [Unknown paths and error bodies](pool.md#unknown-paths-and-error-bodies) covers the same format for the pool endpoints.

---
The machine-readable specification is [openapi.yaml](openapi.yaml). Per-environment endpoints are in [Environments](environments.md), and a copy-paste path to a first successful call is in [Quickstart](quickstart.md).
