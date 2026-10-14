# Users

Read the KYC completion state and card issuance status of the users attributed to your client.

All requests require `Authorization: Bearer <accessToken>`.

| Environment | Base URL |
|---|---|
| Sandbox | `https://api-staging.pay-3.io/functions/v1/external-service` |
| Production | `https://api.pay-3.io/functions/v1/external-service` |

The base URL includes the trailing `/external-service`; the paths below sit directly under it (for example `GET {BASE_URL}/users/{userId}`).

## Scope

| Scope | Covers |
|---|---|
| `users:status` | `GET /users/list` and `GET /users/{userId}` (`users:read` satisfies it automatically) |
| `users:invite` | `PUT /users/{userId}/invite` (`users:write` satisfies it automatically) |

## Visibility

You see only the users attributed to your client. A user is attributed when either of the following holds:

1. They signed up through a link carrying one of your referral codes (the same users the `user.registered` webhook reports). Attribution is fixed at sign-up and does not change if the code is later disabled or deleted.
2. They signed up through the invite link of a user in (1), at any depth. They inherit that user's referral code unchanged, and are part of the same set with no extra step.
3. You created them with `POST /users/register`.

This set is **identical** across `GET /users/list`, `GET /users/{userId}` and `POST /pool/transfer` ([Partner Pool](pool.md)): a user that appears in the list can always be looked up and can always be sent a top-up instruction (other conditions, such as KYC, still apply).

User ids that are not attributed to you, belong to another partner, or do not exist all return **`404`**. `403` is never used here, so the response does not disclose whether a user id exists.

## GET /users/list

Lists the users attributed to your client.

```bash
curl -s "$BASE_URL/users/list?limit=50&offset=0" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

- 200:
  ```json
  {
    "data": [
      {
        "userId": "5c3ff529-0000-4000-8000-000000000000",
        "registeredAt": "2026-09-14T10:11:12.000Z",
        "referralCode": "PARTNER-A",
        "kycStatus": "approved",
        "kyc": { "identity": { "status": "approved" }, "cardIssuer": { "status": "approved" } },
        "cardStatus": "issued",
        "inviteCode": "K7M2Q9XA",
        "invitedByUserId": null,
        "inviteEnabled": false
      }
    ],
    "paging": { "limit": 50, "offset": 0, "total": 1 }
  }
  ```
- With no matching users the response is `{"data": [], "paging": {"limit":50,"offset":0,"total":0}}`. An empty result is not a `404`.
- 400: invalid `limit` / `offset` / `referralCode` / `kycStatus`, or an unaccepted parameter name.
- 403: missing scope.

| Field | Meaning |
|---|---|
| `userId` | Pay3 user id (currently a UUID) |
| `registeredAt` | Registration timestamp (ISO 8601, UTC) |
| `referralCode` | The referral code fixed at sign-up. `null` for users created through `POST /users/register` without one |
| `kycStatus` | Overall status. Same vocabulary and same evaluation as `GET /users/{userId}` (see [kycStatus and kyc](#kycstatus-and-kyc)) |
| `kyc` | Per-stage status `{ identity: { status }, cardIssuer: { status } }` (same as above) |
| `cardStatus` | Summary of card issuance: `issued` or `not_issued` |
| `inviteCode` | The user's own invite code, issued by Pay3 at sign-up (the code their invite link carries) |
| `invitedByUserId` | The user who invited them. `null` for users who signed up with a referral code directly, or were created through `POST /users/register` |
| `inviteEnabled` | Whether you have enabled this user's invite link (see [PUT /users/{userId}/invite](#put-usersuseridinvite)). `false` for users created through `POST /users/register` |

`cardStatus` is a summary flag taken from Pay3's own records. The list performs no per-user card lookup, so a slow or unavailable card platform never blocks it. Card count, form factor and states such as `frozen` come from `cards` in `GET /users/{userId}`.

### Paging

| Parameter | Default | Range | On an invalid value |
|---|---|---|---|
| `limit` | `50` | decimal integer, 1–200 | `400` — values are never silently clamped |
| `offset` | `0` | decimal integer, 0 or greater | `400`. An `offset` past the total returns a `200` empty page (`"data": []`, `total` unchanged) |

- Ordering is fixed: newest `registeredAt` first, ties broken by `userId`. Because the order is fixed, advancing `offset` neither skips nor repeats rows.
- `paging.total` is the number of users attributed to you that match the filters below, before `limit` is applied.
- `limit`, `offset`, `referralCode` and `kycStatus` are **the only accepted parameters**, and names are case-sensitive. Any other name (including a misspelling such as `?userid=`) returns `400`, with the accepted names listed in the body; an unrecognised filter is never silently dropped and returned as an unfiltered `200` (see [Query parameter validation](pool.md#query-parameter-validation)).
- Sort options and CSV export are not currently offered.

### Filters

Both filters are optional and can be combined (a user must match both). An empty value (`?kycStatus=`) means no filter.

| Parameter | Matches | On an invalid value |
|---|---|---|
| `referralCode` | Users who signed up with this code. Case-insensitive exact match; wildcards carry no meaning. A deleted code still matches the users attributed to it | `400` when the value is not 3–64 characters of `A-Z`, `a-z`, `0-9`, `-` and `_`. A well-formed code that is not one of yours returns a `200` empty page |
| `kycStatus` | Users whose `kycStatus` field has this value: `not_submitted`, `pending`, `approved` or `rejected` | `400`, with the accepted values listed in the body |

```bash
curl -s "$BASE_URL/users/list?referralCode=PARTNER-A&kycStatus=approved" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Users created through `POST /users/register` without a referral code never match a `referralCode` filter. Per-code totals are available from [`GET /referral-codes/stats`](referral-codes.md#get-referral-codesstats).

### Reading every page

Advance `offset` by `limit` until you reach `paging.total`. `/pool/ledger` and `/pool/transfers` use the same `paging` shape, so the same loop works there.

```bash
LIMIT=200
OFFSET=0
while : ; do
  PAGE=$(curl -s "$BASE_URL/users/list?limit=$LIMIT&offset=$OFFSET" \
    -H "Authorization: Bearer $ACCESS_TOKEN")
  echo "$PAGE" | jq -c '.data[]'
  TOTAL=$(echo "$PAGE" | jq '.paging.total')
  OFFSET=$((OFFSET + LIMIT))
  [ "$OFFSET" -ge "$TOTAL" ] && break
done
```

- The termination condition is **`offset >= paging.total`**. Looping until `data` comes back empty also works, since an `offset` past the total returns a `200` empty page rather than a `404`.
- If new users register while you are paging, the newest-first order shifts later pages by one row each. When an exact single pass matters, use incremental sync instead: read from the first page until you reach the last user you already have.

## GET /users/{userId}

`userId` is the Pay3 user id delivered by the `user.registered` webhook ([Webhooks](webhooks.md)); it is currently a UUID.

```bash
curl -s "$BASE_URL/users/$USER_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

- 200:
  ```json
  {
    "userId": "5c3ff529-0000-4000-8000-000000000000",
    "kycStatus": "approved",
    "kyc": { "identity": { "status": "approved" }, "cardIssuer": { "status": "approved" } },
    "cards": [
      { "cardType": "virtual", "status": "active" },
      { "cardType": "physical", "status": "shipped" }
    ],
    "inviteCode": "K7M2Q9XA",
    "invitedByUserId": null,
    "inviteEnabled": false
  }
  ```
  - A user with no cards returns `"cards": []`, never `null`.
  - Card number, CVV, BIN, billing address, name and email are not included.
  - `inviteCode`, `invitedByUserId` and `inviteEnabled` mean the same as in [`GET /users/list`](#get-userslist).
- 403: missing scope.
- 404: the user id is not attributed to you, or does not exist.
- 502: card issuance status could not be retrieved. This is distinct from "no cards" — retry rather than treating it as an empty list.

### kycStatus and kyc

Verification runs in **two stages**: a first-line identity check through Sumsub (`identity`), followed by the card issuer's own review (`cardIssuer`). Even after the first stage is approved, cards cannot be issued and top-up instructions cannot be accepted until the issuer's review completes.

- `kycStatus` — the overall status. `approved` means top-up instructions and card issuance will go through.
- `kyc.identity.status` — first-line identity check (Sumsub).
- `kyc.cardIssuer.status` — the card issuer's review.

```json
{
  "kycStatus": "pending",
  "kyc": {
    "identity":   { "status": "approved" },
    "cardIssuer": { "status": "pending" }
  }
}
```

| `kyc.identity.status` | Meaning |
|---|---|
| `not_submitted` | The identity check has not been attempted (the state right after registration) |
| `pending` | Documents submitted, review in progress |
| `approved` | The identity check passed. **Cards still cannot be issued**; the issuer's review starts automatically |
| `rejected` | Rejected. Re-submitting returns the stage to `pending` |

| `kyc.cardIssuer.status` | Meaning |
|---|---|
| `not_started` | The identity check has not finished, so the issuer's review has not begun |
| `pending` | The issuer's review is in progress. Its duration varies from minutes to considerably longer |
| `approved` | The issuer's review passed; cards can be issued and balances topped up |
| `rejected` | The issuer rejected the user |

The overall `kycStatus` is derived as follows.

| `identity` | `cardIssuer` | `kycStatus` |
|---|---|---|
| anything but `approved` | (any) | same value as `identity` |
| `approved` | `approved` | `approved` |
| `approved` | `rejected` | `rejected` |
| `approved` | anything else | `pending` |

`approved` is equivalent to "a top-up instruction will go through": it is the same condition `POST /pool/transfer` evaluates before returning `412` for incomplete KYC, so an `approved` user never receives a `412`. While only the first stage is approved, `kycStatus` stays `pending` and becomes `approved` when the issuer's review passes. That transition is reported by the [`user.kyc.updated`](webhooks.md) webhook, whose `stage` field names the stage that changed.

### cards

| cardType | status | Meaning |
|---|---|---|
| `virtual` | `active` | Issued and immediately usable |
| `virtual` | `issued` | Issuance in progress; not yet usable |
| `physical` | `issued` | Issuance complete, preparing for shipment |
| `physical` | `shipped` | Shipped; unusable until it reaches the cardholder |
| `physical` | `activated` | Activated and usable |
| either | `frozen` | Temporarily suspended, by the user or by support |

- `frozen` takes precedence over the form-factor state: an activated physical card that is locked also reports `frozen`.
- Cancelled and deactivated cards are not listed.

## PUT /users/{userId}/invite

Enables or disables a user's invite link. While disabled (the default for every user), the user's Friends screen shows only "The program hasn't started yet. Please ask the person who invited you for details." Once enabled, it shows their invite link and QR code. Pay3 applies no other condition (KYC or otherwise) — whether to enable is your decision.

People who sign up through that link become your users and inherit the inviter's referral code; the direct inviter is recorded as `invitedByUserId` (see [`user.registered`](webhooks.md)). While a user's invite link is disabled, their invite code is treated as invalid: anyone who signs up with it is registered without a referral and does not become your user. Disabling does not change users who have already signed up; they keep their attribution.

```bash
curl -s -X PUT "$BASE_URL/users/$USER_ID/invite" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

- Body: `{"enabled": true}` or `{"enabled": false}`. `enabled` is the only accepted key.
- 200:
  ```json
  { "userId": "5c3ff529-0000-4000-8000-000000000000", "inviteCode": "K7M2Q9XA", "invitedByUserId": null, "inviteEnabled": true }
  ```
  Repeating the same value also returns `200` (the request is idempotent, so no `Idempotency-Key` is needed).
- 400: `enabled must be a boolean` — `enabled` is missing or not a boolean, or the body has other keys.
- 403: `Insufficient scope: users:invite required`. Clients holding `users:write` satisfy it automatically; clients with no scopes configured do not.
- 404: the user id is not attributed to you, or does not exist.
- 409: `invite_not_available: this user was created without a referral code` — users created through `POST /users/register` without a referral code have no referral code to pass on, so their invite cannot be enabled.

The current state is also returned as `inviteEnabled` by `GET /users/list` and `GET /users/{userId}`. Changing it does not emit a webhook.

## The separate `GET /users?id=`

`GET /users?id=<uuid>` is a different, pre-existing endpoint with a different response shape ([Endpoints](endpoints.md)). For partner integrations, use `GET /users/{userId}`.

---
The machine-readable specification is [openapi.yaml](openapi.yaml).
