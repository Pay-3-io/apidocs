# Partner Pool

Fund a pool balance up front, then instruct charges from that pool onto the card balances of your own users.

All requests require `Authorization: Bearer <accessToken>`.

| Environment | Base URL |
|---|---|
| Sandbox | `https://api-staging.pay-3.io/functions/v1/external-service` |
| Production | `https://api.pay-3.io/functions/v1/external-service` |

The base URL includes the trailing `/external-service`, and every path sits directly under it (`GET {BASE_URL}/pool/balance`). The expanded URL must contain `/external-service` exactly once.

## Scopes

| Scope | Grants |
|---|---|
| `pool:read` | Read balance, ledger, and instructions |
| `pool:transfer` | Create charge instructions (includes `pool:read`) |

A missing scope returns `403 Insufficient scope: <scope> required`.

## Source IP allowlist

Calls made with a token obtained from an API key are accepted only from IP addresses registered under **Developer → Source IPs** in the console. The rule is identical in sandbox and production.

- While no IP is registered, every endpoint returns `403 ip_not_registered`. Console access is unaffected, so you can register addresses at any time.
- A call from an unregistered IP returns `403 ip_not_allowed`.
- The source is taken from the connecting IP. Forwarded headers such as `x-forwarded-for` and `x-real-ip` are ignored, because a client can set them freely.
- IPv4, IPv6, and CIDR entries are accepted, up to 20 entries.

## Money flow

```
You send the deposit asset to the pool deposit address
  → Pay3 confirms the credit, deducts 0.5%, and adds the remainder to the pool balance in USD
  → You call POST /pool/transfer to charge $X to a given user
  → The amount is drawn from the pool balance and applied to the user's card balance
```

The deduction rate is returned as `feeRate` by `GET /pool/deposit_address` (0.5% by default). Upper and lower amount limits are your responsibility: the instructed amount is charged in USD as given.

## GET /pool/balance

Current pool balance, for refill decisions.

```json
{
  "balance": "9950.00",
  "pendingTransfers": "300.00",
  "available": "9650.00",
  "currency": "USD"
}
```

| Field | Meaning |
|---|---|
| `available` | Amount a charge instruction can draw on right now |
| `pendingTransfers` | Amounts reserved by accepted instructions that have not settled |
| `balance` | The sum of the two |

`?currency=USD` is optional; a pool holds a single currency today, so the response is identical either way, but sending it keeps your code unchanged if pools become multi-currency. A value that is not a three-letter currency code returns `400`; a currency other than the pool's returns `404`, the same response as "no pool".

- `404` — no pool account has been opened yet.
- `400` — any other query parameter. This endpoint takes none and always returns the current balance. For a balance at a past point in time, follow `balanceAfter` in `GET /pool/ledger`.

## GET /pool/deposit_address

The pool deposit address. `currency` says what to send, `network` says which chain; both are per-account settings.

```json
{ "address": "T...", "network": "TRON", "currency": "USDT", "feeRate": "0.0050" }
```

| Environment | Deposit rail |
|---|---|
| Sandbox | USDC on Ethereum Sepolia (`network: "ETH_SEPOLIA"`, named explicitly so it is not confused with mainnet `ETH`) |
| Production | USDT on TRON |

- Use the returned `currency` and `network` pair as given. Any other asset sent to the address does not arrive; it can be neither detected nor refunded.
- Sandbox exercises the whole path — address, credit, ledger row, webhook — but it is a different rail from production. Testnet USDC is available from public faucets.
- If `network` is `SANDBOX` and `address` starts with `0xSANDBOX_`, no real address has been issued yet. Do not send funds to it.
- `409` — no deposit address has been issued. Do not send funds.
- `400` — any query parameter. This endpoint takes none and always returns the single registered address, so `?network=TRON` is rejected rather than dropped.

## POST /pool/transfer

Creates a charge instruction. The `Idempotency-Key` header is required.

- Headers: `Idempotency-Key: <unique>`
- Body: `{ "userId": "<uuid>", "amount": "300.00" }`, where `amount` is a string with at most two decimals
- `202`: `{ "transferId": "pt_...", "status": "pending" }`

Completion is not returned synchronously. Observe it through the `pool.transfer.completed` / `pool.transfer.failed` webhooks ([Webhooks](webhooks.md)) or `GET /pool/transfer/{transferId}`.

Re-sending the same `Idempotency-Key` creates only one instruction. The same key with a different amount or user returns `409`, so the result of a `$300` instruction is never returned for a `$3000` request. See [Idempotency](idempotency.md).

### Eligible users

You can charge only users that belong to you, which means either:

1. A user who signed up through one of your referral links ([Referral codes](referral-codes.md)). Attribution is fixed at sign-up and never changes, even if the code is later disabled or deleted.
2. A user you created with `POST /users/register`.

This is exactly the set readable through `GET /users/{userId}` ([Users](users.md)). Any other `userId` — another partner's user, an unattributed user, or an id that does not exist — returns `404` without distinction.

### Errors

| Status | Meaning |
|---|---|
| 400 | `Idempotency-Key` missing, `userId` missing, or `amount` malformed |
| 402 | Insufficient pool balance |
| 404 | User not found (another partner's user returns `404` even if it exists) |
| 409 | Same key sent with a different body, or a request with that key is still in flight |
| 412 | The user's KYC is not approved |
| 429 | Rate limit exceeded |
| 503 | No settlement mode is configured (see [Settlement modes](#settlement-modes)) |

Rejections (402 / 404 / 412, and 409 `pool_not_found`) are recorded with a reason and appear in `GET /pool/transfers` and in the console. Rejection bodies also carry a `transferId` — the id of the recorded rejection row — so your instruction ids map one-to-one to Pay3 ids and the reason can be read back directly.

```json
// 412 (KYC not approved)
{ "message": "User KYC is not approved", "code": 412, "transferId": "pt_9f0c..." }
// 402 (insufficient balance)
{ "message": "Insufficient pool balance", "code": 402, "transferId": "pt_1a7d..." }
```

In the rare case where recording itself fails, no `transferId` is returned, so you never receive an id you cannot read back.

## GET /pool/transfer/{transferId}

State of a single instruction.

```json
{
  "transferId": "pt_...",
  "userId": "<uuid>",
  "amount": "300.00",
  "currency": "USD",
  "status": "settled",
  "reason": null,
  "settlementMode": "simulate",
  "createdAt": "...",
  "settledAt": "...",
  "failedAt": null
}
```

- `status` — `pending` | `settled` | `failed` | `rejected`
- `settlementMode` — `simulate` in sandbox; see [Settlement modes](#settlement-modes).
- `404` — not found (another partner's instruction returns `404` even if it exists).

## GET /pool/transfers

List of instructions, newest `createdAt` first.

- Query: `status`, `userId`, `from`, `to`, `limit`, `offset` — see [Query parameters](#query-parameters)
- `200`: `{ "data": [ ...same shape as GET /pool/transfer... ], "paging": { limit, offset, total } }`

`userId` accepts only a uuid, the same value as `userId` in `GET /users/list`. A well-formed uuid that is not attributed to you returns `200` with `"total": 0`.

```bash
$ curl -s "$BASE_URL/pool/transfers?userId=abc" -H "Authorization: Bearer $TOKEN"
{"message":"userId must be a uuid (e.g. \"3f8c1e2a-5b47-4d9e-8a10-2c6b7d0e4f51\")","code":400}
```

An instruction naming a user you do not own is rejected with `unknown_user`, but the rejection is still recorded, and both the list and the detail response return the `userId` you sent, unchanged. `?userId=` filters those rejected rows too, so any `userId` shown in the list, in the detail response, or in the console can be passed straight back as a filter.

`from` / `to` filter on `createdAt`, the time the instruction was accepted, not on `settledAt`. The ledger records its `transfer` row at acceptance time as well, so the same `from` / `to` select the matching interval in both endpoints.

```bash
# a single day (2026-09-15T00:00:00Z – 23:59:59.999999Z)
curl -s "$BASE_URL/pool/transfers?from=2026-09-15&to=2026-09-15&limit=50" \
  -H "Authorization: Bearer $TOKEN"
```

## GET /pool/ledger

Every movement of the pool balance, newest `createdAt` first.

- Query: `type`, `from`, `to`, `limit`, `offset` — see [Query parameters](#query-parameters)

```json
{
  "data": [
    { "id": "...", "type": "fee", "amount": "-50.00", "balanceAfter": "9950.00",
      "referenceId": "tx-...", "metadata": { "rate": "0.0050" }, "createdAt": "..." },
    { "id": "...", "type": "deposit", "amount": "10000.00", "balanceAfter": "10000.00",
      "referenceId": "tx-...", "metadata": null, "createdAt": "..." }
  ],
  "paging": { "limit": 50, "offset": 0, "total": 5 }
}
```

`balanceAfter` is the running balance immediately after the row is applied. A credit is split into two rows — gross in, then fee out — so in the example above, a credit of 10,000.00 into an empty pool gives `10000.00` on the `deposit` row and `9950.00` on the newer `fee` row. Adding `amount` from the oldest row forward reproduces each `balanceAfter`.

| `type` | Sign | Meaning |
|---|---|---|
| `deposit` | + | A credit applied to the pool (gross, before deduction) |
| `fee` | − | The deduction taken on credit (0.5% by default) |
| `transfer` | − | A charge drawn for a user (written at acceptance) |
| `refund` | + | Return of a failed charge (offsets the `transfer` row with the same `referenceId`) |
| `withdrawal` | − | Pool balance withdrawn back out of USD |
| `adjustment` | ± | Operational adjustment |

Every operation that moves the pool balance writes exactly one row; operations that do not move it write none. For charge instructions:

| Event | Ledger |
|---|---|
| Instruction accepted (202) | A `transfer` row (−) is written at that moment; the balance drops here |
| Instruction becomes `settled` | No new row. `settlement_mode` is added to the `transfer` row's `metadata` |
| Instruction becomes `failed` | A `refund` row (+) offsets the `transfer` row by the same amount |
| Instruction rejected (402 / 404 / 412) | No row, because the balance did not move. The rejection is in `GET /pool/transfers` |

`pending` instructions therefore appear in the ledger, and the balance never drops without a corresponding row. A row's `referenceId` is the `transferId`, so `GET /pool/transfer/{transferId}` gives that row's final state.

`metadata` is free-form per-row detail. `fee` rows carry the rate used as `{"rate": "0.0050"}` — a fixed 4-decimal string, like `feeRate` from `GET /pool/deposit_address`, never a number.

`?type=` accepts exactly one of the six values above; uppercase values and comma-separated lists are not. The console labels a charge drawn for a user differently from the API value, which is `transfer`:

```bash
$ curl -s "$BASE_URL/pool/ledger?type=charge" -H "Authorization: Bearer $TOKEN"
{"message":"type must be one of: deposit, fee, transfer, refund, withdrawal, adjustment","code":400}
```

## Query parameters

On the list endpoints (`GET /pool/transfers`, `GET /pool/ledger`, `GET /users/list`, `GET /referral-codes`) and on `GET /pool/balance`, values and parameter names are validated strictly: out-of-range values, malformed values, and unknown names all return `400` with a body of the form `{ "message": ..., "code": 400 }`, rather than being clamped, ignored, or answered with an empty `200`. A typo is therefore never indistinguishable from "no rows".

| Parameter | Accepted values | Default |
|---|---|---|
| `limit` | Decimal integer 1–200 (`1e2`, `1.5`, `abc`, `-1`, `0`, `201` return 400) | 50 |
| `offset` | Decimal integer 0 or more. An `offset` past the total returns an empty `200` page: `"data": []`, with `"total"` still the filtered total | 0 |
| `from` / `to` | ISO 8601 date `2026-09-14`, or datetime with offset `2026-09-14T00:00:00Z` / `2026-09-14T09:00:00+09:00`. Non-existent dates (`2026-02-30`) return 400. Fractional seconds up to 6 digits, matching the stored precision; 7 or more return 400 | no filter |
| `type` (`/pool/ledger`) | Exactly one of `deposit`, `fee`, `transfer`, `refund`, `withdrawal`, `adjustment` | no filter |
| `status` (`/pool/transfers`) | Exactly one of `pending`, `settled`, `failed`, `rejected` | no filter |
| `userId` (`/pool/transfers`) | A uuid | no filter |

An empty value (`?from=`) means "no filter".

Names are case-sensitive (`userid` is not `userId`), and an unaccepted name returns the list of names that endpoint accepts.

```bash
$ curl -s "$BASE_URL/pool/ledger?userid=abc" -H "Authorization: Bearer $TOKEN"
{"message":"Unknown query parameter \"userid\". Accepted: type, from, to, limit, offset","code":400}
```

| Endpoint | Accepted parameters |
|---|---|
| `GET /pool/ledger` | `type`, `from`, `to`, `limit`, `offset` |
| `GET /pool/transfers` | `status`, `userId`, `from`, `to`, `limit`, `offset` |
| `GET /users/list` | `limit`, `offset` |
| `GET /referral-codes` | (none; always returns all codes) |
| `GET /pool/balance` | (none; always returns the current balance) |
| `GET /pool/deposit_address` | (none; always returns the registered address) |

### Date boundaries

A date-only value is interpreted in UTC.

| Value | Boundary |
|---|---|
| `from=2026-09-15` (date only) | From `2026-09-15T00:00:00Z` |
| `to=2026-09-15` (date only) | Up to `2026-09-15T23:59:59.999999Z` — the whole day is included |
| `from` / `to` with a datetime | The given instant, inclusive at both ends |

A single day is `?from=2026-09-15&to=2026-09-15`; there is no need to pass the next day. To cut a day in a local time zone, pass datetimes with the offset, for example `?from=2026-09-15T00:00:00+09:00&to=2026-09-15T23:59:59+09:00`.

## Unknown paths and error bodies

- Unrecognised paths and unsupported HTTP methods return a JSON `404`: `{ "message": "Unknown endpoint. ...", "code": 404 }`. A misspelling such as `POST /pool/tranfer` never returns success. The `/kyc/*` and `/card/*` subtrees resolve `userId` before routing, so their responses to unknown paths depend on the body ([Endpoints](endpoints.md#unknown-paths-and-error-bodies)).
- A request can be answered at the edge before it reaches the application, in which case the error body is not JSON. Check `content-type` in your error handling and make sure your parser tolerates a non-JSON body.

## Settlement modes

The settlement mode is set per client by Pay3 and cannot be changed through the partner API. `simulate` is the sandbox mode; production values are provided during production onboarding.

- Under `simulate`, funds move from the pool balance to the user's card balance along the same path as in production, so a `settled` instruction really is reflected on the card balance. What the sandbox omits is only the detection of incoming deposits on the production rail; sandbox credits are detected on the sandbox rail and emit `pool.deposit.credited` ([Webhooks](webhooks.md)).
- If funds cannot be moved — insufficient pool funds, or an error on the card platform — the instruction is recorded as `failed` with a reason and the amount is returned to the pool balance.
- A client with no mode configured gets `503` from `POST /pool/transfer`. There is no default, so a missing setting can never produce a ledger row without a matching movement.
- Finalised rows carry `settlementMode`, and the mode is kept in the ledger `metadata`, so sandbox rows never look like production movements.

## Notes

- `userId` accepts Pay3 uuids only.
- A credit that cannot be matched to a pool is recorded as pending and handled by Pay3; it is never discarded silently.
- Withdrawals from the pool balance are handled on request; contact Pay3.

The machine-readable reference for every endpoint and field is `openapi.yaml`.
