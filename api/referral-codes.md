# Referral Codes

Register the referral codes your client uses, and attribute the users who sign up through them.

All requests require `Authorization: Bearer <accessToken>`.

| Environment | Base URL |
|---|---|
| Sandbox | `https://api-staging.pay-3.io/functions/v1/external-service` |
| Production | `https://api.pay-3.io/functions/v1/external-service` |

The base URL includes the trailing `/external-service`; the paths below sit directly under it (for example `GET {BASE_URL}/referral-codes`).

## Scopes

| Scope | Covers |
|---|---|
| `referrals:read` | Listing codes and reading their stats |
| `referrals:write` | Creating, enabling, disabling and deleting codes, and setting their card prices and deposit fee rates (includes `referrals:read`) |

## Code rules

- 3–64 characters of `A-Z`, `a-z`, `0-9`, `-` and `_`.
- **Case-insensitive.** `PARTNER-A` and `partner-a` are the same code and cannot coexist.
- **First come, first served**, unique across all partners, because sign-up links share a single namespace.
- **There is no rename.** To correct a code, delete it and create a new one.

## GET /referral-codes

Lists all of your codes, newest first.

- 200:
  ```json
  {
    "data": [
      { "code": "PARTNER-A", "enabled": true, "label": "Agency A",
        "link": "https://app.pay-3.io/?ref=PARTNER-A",
        "cardPrices": [ { "bin": "45492418", "type": "virtual", "price": "12.00" } ],
        "depositFeeRate": "0.015", "depositFeeRateSource": "code",
        "createdAt": "...", "updatedAt": "..." }
    ],
    "defaultDepositFeeRate": "0.019"
  }
  ```
- `link` is the sign-up link carrying the code. Use the value as returned; the host differs between sandbox and production.
- `cardPrices` is the card issuance price set on the code (see [Card prices per code](#card-prices-per-code)); `[]` when none is set.
- `depositFeeRate` is the fee rate that applies to the code's users when they deposit stablecoins from their own wallet, and `depositFeeRateSource` says where it comes from: `code` (set on this code) or `client` (your client's default). `defaultDepositFeeRate` is your client's default rate. See [Deposit fee rate per code](#deposit-fee-rate-per-code).
- **No query parameters are accepted.** Any parameter returns `400` with a body such as `Unknown query parameter "enabled". Accepted: (none)`, so a filter that looks applied but is not can never be mistaken for a complete list. There is no paging and no filtering.

## GET /referral-codes/stats

Returns sign-ups, KYC approvals and card issuances per code, for reporting by code (for example, by agency).

```bash
curl -s "$BASE_URL/referral-codes/stats?from=2026-09-01&to=2026-09-30" \
  -H "Authorization: Bearer $TOKEN"
```

- 200:
  ```json
  {
    "data": [
      { "code": "PARTNER-A", "registered": 12, "kycApproved": 9,
        "cardsIssued": { "virtual": 7, "physical": 1 }, "issuanceAmount": "91.00" }
    ],
    "from": "2026-09-01",
    "to": "2026-09-30"
  }
  ```
- One row per code: every current code, including codes with no activity (all zeros), and **deleted codes that still have attributed users**, so past figures do not change when a code is deleted.
- Sorted by `registered` (highest first), then by code.
- `from` and `to` in the response echo the query as sent, or `null` when omitted.

| Field | Meaning |
|---|---|
| `registered` | Users who signed up with the code during the period (by sign-up time) |
| `kycApproved` | Of those users, how many currently have `kycStatus` `approved` — the same value `GET /users/{userId}` returns |
| `cardsIssued.virtual` / `cardsIssued.physical` | Issued cards, including cards later deleted, issued during the period to users of the code, by card type. Users count regardless of when they signed up |
| `issuanceAmount` | Total card issuance price charged for those cards (including cards later deleted), in USD, as a string with 2 decimal places (the same format as `POST /card/quote`). Physical card shipping is not included |

Card counts cover issued cards, including cards later deleted, because their issuance price was charged.

### Query parameters

| Parameter | Format | Meaning |
|---|---|---|
| `from` | ISO 8601 date or datetime | Start of the period, inclusive. Omit for no lower bound |
| `to` | ISO 8601 date or datetime | End of the period, inclusive. Omit for no upper bound |

- `from` and `to` mean the same as on `GET /pool/ledger` and `GET /pool/transfers` (see [Date boundaries](pool.md#date-boundaries)). A date-only value is interpreted in UTC, and **a date-only `to` includes that whole day**: September is `?from=2026-09-01&to=2026-09-30`, and a single day is `?from=2026-09-15&to=2026-09-15`. A datetime is the given instant, inclusive at both ends.
- `400` when a date is invalid (the same messages as the pool endpoints), when `from` is later than `to` (`from must not be later than to`), or when any other parameter is sent (`Unknown query parameter ... Accepted: from, to`).

`stats` is also a valid code name: `PATCH /referral-codes/stats` and `DELETE /referral-codes/stats` act on a code named `stats`. Only `GET` returns the stats.

## POST /referral-codes

- body: `{ "code": "PARTNER-A", "label": "Agency A", "enabled": true, "cardPrices": [ { "bin": "45492418", "type": "virtual", "price": "12.00" } ], "depositFeeRate": "0.015" }`
  - `label`, `enabled`, `cardPrices` and `depositFeeRate` are optional; `enabled` defaults to `true`. `label` is a free-form note for your own use and is not shown to end users.
- 201: the single code, in the shape above (without `defaultDepositFeeRate`).
- 400: invalid code format, an invalid `cardPrices` entry, or an invalid `depositFeeRate` (nothing is created).
- 409: the code is already taken, by you or by another partner, or it matches (case-insensitively) a user's invite code. Users' invite codes and referral codes share one namespace at sign-up, so a code that collides with one is rejected.

## PATCH /referral-codes/{code}

Enables or disables a code, and sets its card prices and deposit fee rate. `enabled`, `cardPrices` and `depositFeeRate` are the only mutable fields; send any combination of them.

- body: `{ "enabled": false }`, `{ "cardPrices": [ { "bin": "45492418", "type": "virtual", "price": "15.00" } ] }` or `{ "depositFeeRate": "0.015" }`
- 200: the updated code.
- 400: an attempt to change anything other than `enabled`, `cardPrices` or `depositFeeRate` (renaming means delete, then create), an invalid `cardPrices` entry, or an invalid `depositFeeRate`. Nothing is changed.
- 404: no such code for your client.

A disabled code stops attributing new sign-ups — `POST /users/register` returns `400` for it. **Users already attributed keep their attribution.**

## DELETE /referral-codes/{code}

- 200: `{ "code": "PARTNER-A", "deleted": true }`
- 404: no such code for your client.

Attribution is fixed at sign-up, so deleting a code changes neither past attribution nor reporting. Deletion cannot be undone.

The card prices and deposit fee rate of a deleted code keep applying to the users who signed up with it. If you later create the same code again, the prices and rate sent with that `POST` (none, if omitted) replace them for all of its users.

Codes are matched exactly, case-insensitively. Wildcard characters carry no meaning in the path: `%` and `_` are not expanded, so bulk deletion is not possible.

## Card prices per code

Set a card issuance price on a code to charge the users who signed up with it a different price, for example one code per agency in each country.

```json
"cardPrices": [
  { "bin": "45492418", "type": "virtual", "price": "12.00" }
]
```

| Field | Rule |
|---|---|
| `bin` | The card BIN, as a 6–8 digit string |
| `type` | `virtual` or `physical` |
| `price` | USD, as a number or string with up to 2 decimal places (`12`, `"12.5"`, `"12.00"`) |

- **The price a user pays is decided in this order:** the price of the code the user signed up with, then your client's default price, then the standard Pay3 price. `POST /card/quote` returns the price that applies to the user.
- **Changing a code's price applies to all of its users at once**, from their next card issuance. Cards already issued are not affected.
- **`cardPrices` replaces the whole set.** Entries you leave out are removed; `[]` removes every price from the code.
- A price must be above the issuance cost of that card (for physical cards, including production). A price at or below it returns `400` and nothing is saved. Shipping for physical cards is charged separately and is not part of `price`.
- Up to 20 entries per code, one per `bin` and `type`.
- `GET /card/catalog` lists the cards you can set a price for and the price that applies when a code has none ([Endpoints](endpoints.md#get-cardcatalog)).

## Deposit fee rate per code

Set a deposit fee rate on a code to charge the users who signed up with it a different fee when they deposit stablecoins from their own wallet. The fee is your revenue in full.

```json
"depositFeeRate": "0.015"
```

| Value | Meaning |
|---|---|
| `"0"` to `"0.05"` | The rate as a decimal fraction (`"0.015"` is 1.5%), as a number or string with up to 5 decimal places |
| `null` | Removes the rate from the code; your client's default rate applies again |

- **The rate a user pays is decided in this order:** the rate of the code the user signed up with, then your client's default rate. The standard Pay3 rate is never used for your users. `"0"` on a code means no fee for its users, even when your default is higher.
- **Changing a code's rate applies to all of its users at once**, from their next deposit. Deposits already received are not affected.
- It applies only to deposits users make from their own wallet. Charges from your pool to a user (`POST /pool/transfer`) are free, and the fee on deposits to your pool is separate (see [Pool](pool.md)).
- A rate above `0.05` or with more than 5 decimal places returns `400` and nothing is saved.

## Attributing users

Pass `referral_code` to `POST /users/register` to attribute the new user to that code.

```bash
curl -X POST "$BASE_URL/users/register" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
        "signup_type": "EMAIL",
        "signup_type_id": "taro@example.com",
        "first_name": "Taro",
        "referral_code": "PARTNER-A"
      }'
```

- On success the response carries `referralCode`, or `null` if no attribution was made.
- **Only codes issued by your own client are accepted.** A code belonging to another partner returns the same `400`, with a byte-identical body, as a code that does not exist.
- **An unknown or disabled code returns `400` and no user is created.** Ignoring it silently would leave a user who carried a code but was never attributed.
- Attribution is **one code per user** and is never overwritten later.

### Sign-up links (`?ref=`)

Users who sign up through the `link` returned by `GET /referral-codes` are attributed to that code at sign-up and reported by the `user.registered` webhook ([Webhooks](webhooks.md)). They appear in `GET /users/list` with the same `referralCode` value.

Each of those users also has their own invite code, issued by Pay3 (`inviteCode` in `user.registered` and the user endpoints). People who sign up through that user's invite link become your users too and **inherit the inviter's referral code** — the same price and deposit fee settings apply, and they count toward that code in `GET /referral-codes/stats`. The direct inviter is reported as `invitedByUserId`. A user's invite link is disabled by default; enable it with `PUT /users/{userId}/invite` ([Users](users.md#put-usersuseridinvite)). Sign-ups with the invite code of a user whose link is disabled are registered without a referral and do not become your users. Disabling a referral code does not disable the invite links of users who signed up with it — control those per user.

---
The machine-readable specification is [openapi.yaml](openapi.yaml). See also [Users](users.md) for reading the attributed users and their status.
