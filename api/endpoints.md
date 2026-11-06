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

Every `/kyc/*` and `/card/*` call (except `GET /card/catalog`) takes a `userId` in the JSON body. Common outcomes for it:

| Case | Status | Body |
|---|---|---|
| `userId` missing | 400 | `{ "message": "User ID is required", "code": 400 }` |
| `userId` unknown, not a UUID, or belongs to another client | 404 | `{ "message": "User not found", "code": -1 }` (`code` does not match the HTTP status) |
| Body is not a JSON object | 400 | `{ "message": "Invalid JSON body", "code": 400 }` |

Failures reported by Pay3's card or identity platform keep their HTTP status: a `4xx` there is returned to you with the same status and a plain-text `message`; only Pay3-side faults are `500`, which you may retry as-is.

### POST /kyc/access-token

Issues a Sumsub access token so you can run the identity verification flow in your own UI. See [Quickstart §3](quickstart.md#3-run-kyc) for the WebSDK recipe.

- body: `{ userId }`
- 200: `{ message, data: { accessToken, userId }, code: 0 }`

### POST /kyc/submit

Call this after identity verification completes (`reviewStatus: completed`, `reviewAnswer: GREEN` in the WebSDK) to start account and card-platform setup. **Idempotent** — an [Idempotency-Key](idempotency.md) is recommended.

- headers: `Idempotency-Key: <unique>`
- body: `{ userId, applicantId }`
- 200: `{ message, data: { applicantId }, code: 0 }`

| Status | Body `message` | Meaning |
|---|---|---|
| 400 | `Applicant ID is required` | `applicantId` missing |
| 400 | `Applicant ID does not belong to this user` | The applicant was created for a different user |
| 404 | `applicant_not_found` | The applicant could not be resolved at setup time |
| 409 | `Idempotency-Key was already used with a different request body` | Same key, different body |

Setup runs asynchronously; this call only starts it. Wait for `GET /users/{userId}` → `kycStatus: "approved"` (or the `user.kyc.updated` webhook) before funding the user or issuing a card.

## Card

### Card programs

Pay3 runs two kinds of card. Every card, catalog entry, quote and transaction says which one it belongs to in a `program` field:

| `program` | What it is |
|---|---|
| `"standard"` | A prepaid balance card. The user's balance is funded first (for example with [`POST /pool/transfer`](pool.md)), and spending draws it down. This is the default and is what every client has today |
| `"collateral"` | A card backed by a crypto collateral contract. Spending power is the collateral minus what is in use, not a prepaid balance. Pay3 enables it per user, and only in sandbox for now. The application, consent and contract setup happen in the Pay3 app, not through this API |

Pay3 decides which program handles each call. The rules are the same as in the Pay3 app, and you never pass a program to card operations:

| Call | Which program handles it |
|---|---|
| `quote`, `issue_card` | The program of the `bin` (as listed by `GET /card/catalog`). Without `bin`, `standard` |
| `lock_card`, `unlock_card`, `set_card_pin` | The program the card was issued under, looked up from Pay3's own issuance records for that user. A `cardId` that is not one of the user's cards returns 404, as before |
| `fetch_cards` | Every program enabled for the user, merged into one list (`standard` cards first) |
| `fetch_deposit_address`, `fetch_transactions`, `issuance_events` | `standard` |

A user without `collateral` enabled sees exactly what they saw before: `standard` only, with the same behaviour.

Some operations exist on only one program. Calling them for the other returns **400 without doing anything**:

| Operation | `standard` | `collateral` |
|---|---|---|
| `quote` | yes | no (issuance is free) |
| `issue_card` | yes | yes (virtual only, `amount` must be `0`) |
| `fetch_cards`, `lock_card`, `unlock_card` | yes | yes |
| `set_card_pin` | yes | no (there are no physical cards) |

```json
{ "message": "set_card_pin is not supported for program collateral", "code": 400 }
```

### POST /card/application/start

Starts the card application, or returns the one already in progress.

- body: `{ userId }`
- 200: `{ message, data: { application: { id, created_at, user_id, whitelisted, code_redeemed, phone_verified, email_verified, kyc_verified, personal_data, billing_data, order_data, card_issued, card_issued_on, card_id, kyc_status } }, code: 0 }`
- 404: `{ "message": "No ongoing card application present", "code": 404 }` when no application could be started.

`issue_card` starts an application on its own, so you do not need to call this before issuing.

### POST /card/application

Returns the card application in progress.

- body: `{ userId }`
- 200: same shape as `application/start`.
- 404: `{ "message": "No ongoing card application present", "code": 404 }` — the user has no application in progress (none was started, or the last one ended with an issued card).

### POST /card/quote

Prices an issuance before you commit to it. **No funds move** — the call is purely informational.

- body: `{ userId, type?, bin?, country? }`
  - `type` (default `"physical"`): `"virtual"` \| `"physical"`. Always pass it explicitly to quote a virtual card.
  - `bin` (optional): see [Card BINs](#card-bins). Omitted, the first BIN that supports the requested form factor is used.
  - `country` (optional): destination. **Required for `physical`** to get a shipping fee — without it `shipping` and `total` come back `null` and issuance is refused.
- 200: `{ data: { bin, form_factor, country, currency, price, shipping, total, program }, code: 0 }`
  - `price` is the issuance fee. `shipping` is the delivery fee, charged **on top of** `price` and paid in full by the cardholder.
  - `total` (= `price` + `shipping`) is the amount actually charged at issuance. **Fund the user's balance for `total`, not `price`.**
  - `price`, `shipping` and `total` are **fixed 2-decimal strings** (`"5.00"`), like every other money field.
  - `shipping` is `null` for virtual cards, when `country` is omitted, and when the carrier fee cannot be retrieved. **`null` means "not available", not "free"** — `total` is then `null` too, and `issue_card` returns 400 (`Shipping quote unavailable, please retry`).
  - The quote is held for **48 hours**; issuing within that window charges exactly the quoted `total`. After that the fee is re-quoted at issuance.
  - `program`: the [card program](#card-programs) that would issue this card.
  - For a user who can apply Pay3 points (P3P) to the issuance fee, the quote also carries the breakdown:
    `issuance_fee` (= `price`), `points_applied` (integer points), `points_applied_usd`, `charge` (cash still due: `issuance_fee` − `points_applied_usd` + `shipping`) and `required_balance` (balance needed before issuing).
    The USD values are fixed 2-decimal strings. `charge` and `required_balance` are `null` when `shipping` is unknown.
    These keys are absent for users that cannot use points (most partner users), so do not rely on them being present.

```json
{ "bin": "45492418", "form_factor": "virtual", "country": null, "currency": "USD", "price": "5.00", "shipping": null, "total": "5.00", "program": "standard" }
```

```json
{ "bin": "45492418", "form_factor": "physical", "country": "JP", "currency": "USD", "price": "100.00", "shipping": "12.00", "total": "112.00", "program": "standard" }
```

> Changed 2026-09-22: `estimated_shipping` (a non-charged indication) was replaced by `shipping` (the fee actually charged). Physical shipping is now billed separately from the issuance fee.

- 400: unsupported `bin` / `type` combination (`{ "message": "Unsupported card bin/form factor: <bin>/<form factor>", "code": 400 }`), or a `bin` of the `collateral` program (`card_quote is not supported for program collateral`).

### GET /card/catalog

Lists the cards your users can be issued, with the price that applies when no other price is set. Scope: `card:read`.

- query: none (any parameter returns 400)
- 200: `{ data: [{ bin, type, name, defaultPrice, program }] }`
  - One entry per BIN and `type` (`"virtual"` \| `"physical"`) that is enabled in the [card BIN catalog](#card-bins) and available to your client.
  - `defaultPrice` is the issuance price for a user without a price of their own — for example a user whose [referral code](referral-codes.md) has no `cardPrices` for that card. It is a **fixed 2-decimal string**, like `price` in `/card/quote`.
  - `program`: the [card program](#card-programs) of that BIN. The catalog is per client, so it lists `standard` cards. `collateral` cards are enabled per user and are not listed here.
  - Costs are never returned.

```json
{ "data": [
  { "bin": "45492418", "type": "virtual", "name": "Pay3 Card", "defaultPrice": "5.00", "program": "standard" }
] }
```

Per-user restrictions set by Pay3 can still narrow what an individual user can be issued; `/card/quote` returns the exact amount for a given user.

### POST /card/issue_card

Issues a card. **Idempotent** — an [Idempotency-Key](idempotency.md) is strongly recommended. KYC must be complete.

- headers: `Idempotency-Key: <unique>`
- body: `{ userId, type, amount?, bin? }`
  - `type`: `"virtual"` \| `"physical"`
  - `amount`: omit it, or send `0`. **Any other value returns 400** (`amount is not supported on this endpoint; fund the user with POST /pool/transfer`). Fund the user's balance with [`POST /pool/transfer`](pool.md) before issuing; the issuance price is managed by Pay3.
  - `bin` (optional): omitted, the first BIN that supports the form factor is used (`537100` for virtual in sandbox).
- 200: `{ data: { id, cardType, status, last4, program }, code: 0 }`
  - `id`: card ID, the same value as `cardId` in the `card.issued` webhook ([Webhooks](webhooks.md)).
  - `cardType`: `"virtual"` \| `"physical"`; `status`: `"active"` \| `"issued"` \| `"shipped"` \| `"activated"` \| `"frozen"`.
  - `last4`: last four digits of the card number. **PAN, CVV, expiry, billing address and email are never returned.**
  - `program`: the [card program](#card-programs) that issued the card (the program of `bin`).
  - These five fields are the entire response; the card platform's raw payload is not passed through.
- 400: `bin` unknown, disabled, or not allowed for that form factor; `amount` other than `0`. **A user balance below the issuance price also returns this 400** — see below.
- 402: the balance ran out mid-issuance — see below.
- 403: **two distinct cases; branch on `message`** (both carry `code: 403`).

  | message | Meaning | What to do |
  |---|---|---|
  | `This card is not available for your account` | The `bin` is not permitted for this account | Retry with a permitted `bin` |
  | `Card limit reached for your account` / `Card limit reached for this card type` | The **card count limit** has been reached | Review the user's existing cards; contact Pay3 if the limit needs raising |

  The default limit is 1 virtual and 1 physical card per user, but it is a configurable safety limit that may differ per client. **Do not hard-code the count — branch on the 403 `message`.** Changing the `bin` does not clear a limit error.
- 409: **three distinct cases; branch on `message`** (all carry `code: 409`). No card is created and no `card.issued` webhook is sent in any of them.

  | message | Meaning | What to do |
  |---|---|---|
  | `Account setup is not complete yet` | The user's account on the card platform does not exist yet — `kyc/submit` starts that setup asynchronously. Checked **before** the balance, so this comes first even when the balance is also short | Wait for `GET /users/{userId}` → `kycStatus: "approved"` (or the `user.kyc.updated` webhook), then retry. This response does **not** consume the `Idempotency-Key`, so the same key can be reused |
  | `Card issuance did not complete: no card was created. ...` | Setup looked complete but issuance still produced no card | Confirm setup, then retry with a **new `Idempotency-Key`**. Contact Pay3 if it repeats |
  | `Idempotency-Key was already used with a different request body` / `A request with this Idempotency-Key is already in progress` | Key reuse ([Idempotency](idempotency.md)) | Use a new key for a new request |

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
- 200: `{ data: [{ id, cardType, status, last4, currency, balance, program }], failedPrograms?, code: 0 }`
  - `balance` is a **fixed 2-decimal string** (`"2.60"`). When it cannot be retrieved it is `null` — never rounded to `"0.00"`, so a zero balance stays distinguishable from a missing one.
  - `currency` is an ISO currency code (for example `"USD"`); `last4` is the last four digits of the card number.
  - `program`: the [card program](#card-programs) of the card. Later operations on the card go to that program automatically.
  - When the user has more than one program enabled, the list merges all of them. If one program cannot be read, the cards of the others are still returned and `failedPrograms` lists the one that failed (for example `["collateral"]`). Retry later for the missing cards. `failedPrograms` is absent when nothing failed. If every program fails, the error of the `standard` program is returned as before.
  - These seven fields are the entire card object. Card-platform internal identifiers, billing address, email, price lists and feature flags are not included.
  - Card type, status and last four digits are also available per user from `cards` in `GET /users/{userId}` ([Users](users.md)).
  - **Card details (card number, CVV, expiry) never cross the partner boundary**; there is no endpoint that returns them.

### POST /card/fetch_deposit_address

Returns the user's crypto deposit address for one token and network. Funds sent to it are credited to the user's balance (less the deposit fee).

- body: `{ userId, token, network }`

  | token | Accepted `network` values |
  |---|---|
  | `USDT` | `TRX`, `TON`, `AVAX`, `ETH`, `SOL`, `BNB` |
  | `USDC` | `OP`, `MATIC` |

  Values are case-sensitive.
- 200: `{ message, data: { address, token, network }, code: 0 }` — `token` and `network` echo the request.

| Status | Body `message` | Meaning |
|---|---|---|
| 400 | `token must be one of: USDT, USDC` / `network for <token> must be one of: …` | Combination not in the table above. Nothing is created |
| 409 | `Account setup is not complete yet` | The user's account does not exist yet. Wait for `kycStatus: "approved"` |
| 4xx | (platform message) | Refused by the card platform for this user's state |

### POST /card/set_card_pin

Sets the ATM PIN of a physical card (and activates the card if it is not active yet).

- body: `{ userId, cardId, pin }` — `pin` is a string of **exactly 6 digits** (`"482915"`).
- 200: `{ "message": "Card pin set successfully", "code": 0 }`

| Status | Body `message` | Meaning |
|---|---|---|
| 400 | `pin must be exactly 6 digits` / `cardId is required` | Rejected before reaching the card platform |
| 400 | `set_card_pin is not supported for program collateral` | The card is a `collateral` card, which has no PIN |
| 404 | `Card not found` | `cardId` is not one of this user's cards |
| 500 | `Failed to set ATM pin` / `Failed to get card` | The card platform did not confirm the change. Retry |

### POST /card/lock_card and POST /card/unlock_card

Locks (freezes) or unlocks a card.

- body: `{ userId, cardId }`
- 200: `{ message, data: { id, status }, code: 0 }`
  - `status` uses the same vocabulary as `fetch_cards`: after `lock_card` it is `"frozen"`; after `unlock_card` it is `"active"` (virtual) or `"activated"` (physical).

| Status | Body `message` | Meaning |
|---|---|---|
| 400 | `cardId is required` | |
| 403 | `Card unlock is restricted for this account. …` (unlock only) | Pay3 has restricted unlocking for this user. Contact Pay3 |
| 404 | `Card not found` | `cardId` is not one of this user's cards |
| 500 | `Card status could not be confirmed. …` | The platform did not return the card. Check with `fetch_cards` before retrying |

### POST /card/fetch_transactions

Returns the user's card transaction history, newest first.

- body: `{ userId, page?, limit? }`
  - `page`: integer `0` or greater, **0-based** (default `0`).
  - `limit`: integer from `1` to `100` (default `20`).
  - Integers may be sent as JSON numbers or as digit-only strings. Anything else returns `400`.
- 200: `{ message, data: [Transaction], paging: { page, limit, hasMore }, transactions: [Transaction], code: 0 }`
  - `hasMore: true` means the next `page` may have more rows.
  - **`transactions` is deprecated**: it carries the same array as `data` and will be removed in a later release. Read `data`.
  - A user whose account has not been set up yet gets `200` with an empty `data` (there are no transactions), not an error.

Transaction:

| Field | Type | Notes |
|---|---|---|
| `id` | string | |
| `kind` | `"deposit"` \| `"spend"` \| `"fee"` \| `"reward"` \| `"issuance"` | |
| `status` | `"completed"` \| `"pending"` \| `"declined"` | |
| `title` | string | Display label: the merchant name for card payments, otherwise a short English label (`Deposit`, `Card issuance fee`, …) |
| `amount` | string \| null | **Signed fixed 2-decimal string** from the user's point of view: deposits positive, refunds and reversals positive (money credited back), purchases and fees negative (`"-12.50"`). `null` if it could not be read — never `"0.00"` in that case |
| `currency` | string | ISO code, for example `"USD"` |
| `occurredAt` | string | ISO 8601 timestamp |
| `merchant` | object \| null | `{ name, city?, country?, mcc? }` for card payments; `null` otherwise |
| `cardId` | string \| null | The card the transaction belongs to, if any |
| `program` | `"standard"` \| `"collateral"` | The [card program](#card-programs) the transaction comes from. This endpoint reads the `standard` program, so it is `"standard"` today |

```json
{ "id": "tx_01", "kind": "spend", "status": "completed", "title": "AMAZON", "amount": "-12.50", "currency": "USD",
  "occurredAt": "2026-10-01T09:12:00Z", "merchant": { "name": "AMAZON", "city": "Seattle", "country": "US", "mcc": "5999" }, "cardId": "<card id>", "program": "standard" }
```

| Status | Body `message` | Meaning |
|---|---|---|
| 400 | `page must be an integer of 0 or greater` / `limit must be an integer between 1 and 100` | |

## Partner Pool

Tops up user balances from a pool deposit: balance, transfer instructions and ledger. Optional, enabled per client by Pay3. → **[Partner Pool](pool.md)**

- `GET /pool/balance` / `GET /pool/deposit_address`
- `POST /pool/transfer` (`Idempotency-Key` required)
- `GET /pool/transfer/{transferId}` / `GET /pool/transfers` (`status` / `userId` / `from` / `to` / `limit` / `offset`)
- `GET /pool/ledger` (`type` / `from` / `to` / `limit` / `offset`)

The list endpoints (`/pool/transfers`, `/pool/ledger`, `/users/list`, `GET /referral-codes`, `GET /referral-codes/stats`) accept **a fixed set of parameter names and reject anything else with 400**, so a misspelling never comes back as an unfiltered `200` (see [Query parameter validation](pool.md#query-parameter-validation)).

`from` and `to` filter on `createdAt`. **A date-only value is interpreted in UTC and `to` covers the whole day**, so a single day is `?from=2026-09-15&to=2026-09-15` (see [Date boundaries](pool.md#date-boundaries)).

## Referral Codes

Register, enable, disable and delete referral codes, set their card prices and deposit fee rates, and attribute users to them. → **[Referral Codes](referral-codes.md)**

- `GET /referral-codes` / `POST /referral-codes`
- `PATCH /referral-codes/{code}` / `DELETE /referral-codes/{code}`
- `GET /referral-codes/stats` (`from` / `to`, same date boundaries as the pool endpoints) — sign-ups, KYC approvals and card issuances per code

`POST /users/register` accepts a `referral_code`.

## User Status

List your users and read their KYC and card issuance status. → **[Users](users.md)**

- `GET /users/list` (scope `users:status`; accepts only `limit` 1–200, `offset`, `referralCode` and `kycStatus`)
- `GET /users/{userId}` (scope `users:status`; unattributed and non-existent ids both return 404)
- `PUT /users/{userId}/invite` (scope `users:invite`, satisfied by `users:write`; enables or disables the user's invite link)

The set of users returned by the list, accepted by the lookup, and accepted by `POST /pool/transfer` is **identical**.

`referralCode` from `GET /users/list` and `partnerRefCode` from the `user.registered` webhook are **the same value** — the referral code fixed at that user's sign-up. The two spellings are per-channel; the values match directly.

## Credentials, webhooks and source IPs

API key issuance and revocation, the webhook endpoint and signing key, and the source-IP allowlist are all managed in the **Developer menu of the partner console**.

Secrets — API keys and signing keys — are shown in clear text only once, at the moment of issuance; if you lose a copy, re-issue it in the console.

## Unknown paths and error bodies

Unrecognised paths and unsupported HTTP methods return a **JSON 404** on every subtree (`/pool/*`, `/referral-codes*`, `/users/*`, `/oauth/*`, `/kyc/*`, `/card/*`):

```json
{ "message": "Unknown endpoint. Check the HTTP method and path against docs/api.", "code": 404 }
```

The path and method are checked **before** the body is read, so a misspelled path or a wrong method (for example `GET /card/fetch_cards`) returns this 404 whatever body you sent.

The unparseable-body outcome is uniform across every subtree: broken JSON, an empty body, or a body that is not a JSON object (`null`, a string, a number, an array) returns **`400 {"message":"Invalid JSON body","code":400}`**. There is no `text/plain` `500` — input errors are never reported as `500` ([Authentication](authentication.md)).

→ [Unknown paths and error bodies](pool.md#unknown-paths-and-error-bodies) covers the same format for the pool endpoints.

---
The machine-readable specification is [openapi.yaml](openapi.yaml). Per-environment endpoints are in [Environments](environments.md), and a copy-paste path to a first successful call is in [Quickstart](quickstart.md).
