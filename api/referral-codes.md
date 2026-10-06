# Referral Codes

Register the referral codes your client uses, attribute the users who sign up through them, and set a card issuance price and a deposit fee rate per code.

All requests require `Authorization: Bearer <accessToken>`.

| Environment | Base URL |
|---|---|
| Sandbox | `https://api-staging.pay-3.io/functions/v1/external-service` |
| Production | `https://api.pay-3.io/functions/v1/external-service` |

The base URL includes the trailing `/external-service`; the paths below sit directly under it (for example `GET {BASE_URL}/referral-codes`).

## Scopes

| Scope | Covers |
|---|---|
| `referrals:read` | Listing codes |
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
- `cardPrices` is the set of card issuance prices on the code, sorted by `bin` then `type`; `[]` when none is set. `price` is USD as a fixed 2-decimal string. See [Card prices per code](#card-prices-per-code).
- `depositFeeRate` is the deposit fee rate that currently applies to the code's users, as a decimal string (`"0.015"` is 1.5%, `"0"` is no fee). `depositFeeRateSource` says where it comes from: `code` (set on this code) or `client` (no rate on the code, so your client's default applies).
- `defaultDepositFeeRate` (top level, list only) is your client's default rate — the rate for codes with no rate of their own. See [Deposit fee rate per code](#deposit-fee-rate-per-code).
- `updatedAt` changes when `enabled` changes. Setting prices or the rate does not change it.
- **No query parameters are accepted.** Any parameter returns `400` with a body such as `Unknown query parameter "enabled". Accepted: (none)`, so a filter that looks applied but is not can never be mistaken for a complete list. There is no paging and no filtering.

There is no endpoint for reading a single code; use this list, or the response of `POST` / `PATCH`.

## POST /referral-codes

```bash
curl -X POST "$BASE_URL/referral-codes" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
        "code": "PARTNER-A",
        "label": "Agency A",
        "cardPrices": [
          { "bin": "45492418", "type": "virtual", "price": "12.00" }
        ],
        "depositFeeRate": "0.015"
      }'
```

| Field | Required | Notes |
|---|---|---|
| `code` | yes | See [Code rules](#code-rules) |
| `label` | no | Free-form note for your own use. Not shown to end users |
| `enabled` | no | Defaults to `true` |
| `cardPrices` | no | Card issuance prices for the code's users. Omitted (or `[]`): no code prices, so your client's default price applies. See [Card prices per code](#card-prices-per-code) |
| `depositFeeRate` | no | Deposit fee rate for the code's users. Omitted (or `null`): no code rate, so your client's default rate applies. See [Deposit fee rate per code](#deposit-fee-rate-per-code) |

- 201: the single code, in the shape above (without `defaultDepositFeeRate`):
  ```json
  { "code": "PARTNER-A", "enabled": true, "label": "Agency A",
    "link": "https://app.pay-3.io/?ref=PARTNER-A",
    "cardPrices": [ { "bin": "45492418", "type": "virtual", "price": "12.00" } ],
    "depositFeeRate": "0.015", "depositFeeRateSource": "code",
    "createdAt": "2026-01-15T09:30:00.000Z", "updatedAt": "2026-01-15T09:30:00.000Z" }
  ```
- 400: invalid code format, an invalid `cardPrices` entry, or an invalid `depositFeeRate` (see [Errors](#errors)). **Nothing is created.**
- 409: the code is already taken, by you or by another partner.
- 500 `Failed to create code`: the code could not be saved together with its prices and rate. **The code is not created** — it is never left in place with the default price or rate. Retry the same request.

## PATCH /referral-codes/{code}

Enables or disables a code, and sets or clears its card prices and deposit fee rate. `enabled`, `cardPrices` and `depositFeeRate` are the only mutable fields. Send **at least one** of them; fields you omit are left unchanged.

```bash
# Change the card price and the deposit fee rate
curl -X PATCH "$BASE_URL/referral-codes/PARTNER-A" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
        "cardPrices": [
          { "bin": "45492418", "type": "virtual", "price": "15.00" }
        ],
        "depositFeeRate": "0.02"
      }'
```

| Body | Effect |
|---|---|
| `{ "enabled": false }` | Disables the code. Prices and rate are unchanged |
| `{ "cardPrices": [ ... ] }` | **Replaces the whole set** of card prices. Entries you leave out are removed |
| `{ "cardPrices": [] }` | Removes every card price from the code; your client's default price applies again |
| `{ "depositFeeRate": "0.02" }` | Sets the code's deposit fee rate |
| `{ "depositFeeRate": null }` | Removes the code's rate; your client's default rate applies again |

- `cardPrices` cannot be `null`; send `[]` to remove the prices.
- 200: the updated code, in the same shape as the `POST` response.
- 400: an empty body, a field other than `enabled`, `cardPrices` or `depositFeeRate` (renaming means delete, then create), an invalid `cardPrices` entry, or an invalid `depositFeeRate` (see [Errors](#errors)). **Nothing is changed.**
- 404: no such code for your client.
- 500 `Failed to update card prices` / `Failed to update deposit fee rate`: the change was not fully saved. Re-send the same request; applying the same values again is safe.

The `POST` and `PATCH` responses read the saved state back. In the rare case that read fails after a successful save, `cardPrices` comes back as `[]` and `depositFeeRate` / `depositFeeRateSource` are omitted; `GET /referral-codes` returns the authoritative state.

A disabled code stops attributing new sign-ups — `POST /users/register` returns `400` for it. **Users already attributed keep their attribution.**

## DELETE /referral-codes/{code}

- 200: `{ "code": "PARTNER-A", "deleted": true }`
- 404: no such code for your client.

Attribution is fixed at sign-up, so deleting a code changes neither past attribution nor reporting. Deletion cannot be undone.

The card prices and deposit fee rate of a deleted code keep applying to the users who signed up with it. If you later create the same code again, the prices and rate sent with that `POST` (none, if omitted) replace them for all of its users.

Codes are matched exactly, case-insensitively. Wildcard characters carry no meaning in the path: `%` and `_` are not expanded, so bulk deletion is not possible.

## Card prices per code

Set a card issuance price on a code to charge the users who signed up with it a different price — for example, one code per agency, each with its own price.

```json
"cardPrices": [
  { "bin": "45492418", "type": "virtual", "price": "12.00" }
]
```

| Field | Rule |
|---|---|
| `bin` | The card BIN, as a string of 6–8 digits |
| `type` | `"virtual"` or `"physical"` |
| `price` | USD, as a number or a string with up to 2 decimal places (`12`, `"12.5"`, `"12.00"`). Greater than `0`, at most `10000` |

- Use the `bin` / `type` pairs listed by [`GET /card/catalog`](endpoints.md#get-cardcatalog). Its `defaultPrice` is the price that applies when a code has no price for that card.
- **The price a user pays is decided in this order:** a price Pay3 has set for that individual user (if any), then the price of the code the user signed up with, then your client's default price, then the standard Pay3 price. `POST /card/quote` returns the price that applies to a given user.
- **A code's price applies to every user who signed up with that code**, from their next card issuance. Cards already issued are not affected.
- **`cardPrices` replaces the whole set** on every `POST` and `PATCH`. Entries you leave out are removed; `[]` removes all of them.
- **A price must be above the issuance cost of that card** (for physical cards, the cost including production). A price at or below it returns `400` (`amount for bin <bin> is below the minimum chargeable price`) and nothing is saved. The cost itself is not disclosed.
- Shipping for physical cards is charged separately and is not part of `price`.
- Up to 20 entries per code, with at most one entry per `bin` and `type`.

## Deposit fee rate per code

Set a deposit fee rate on a code to charge the users who signed up with it a different fee when they deposit stablecoins from their own external wallet to their card.

```json
"depositFeeRate": "0.015"
```

| Value | Meaning |
|---|---|
| `"0"` to `"0.05"` | The rate as a decimal fraction (`"0.015"` is 1.5%), as a string or a number, with up to 5 decimal places. The string form is recommended |
| `null` | No rate on the code; your client's default rate applies |

- **The rate a user pays is decided in this order:** a rate Pay3 has set for that individual user (if any), then the rate of the code the user signed up with, then your client's default rate. If none of these is set, no fee is charged. The standard Pay3 rate for its own app users is never applied to your users.
- `"0"` on a code means no fee for its users, even when your client's default rate is higher.
- **A code's rate applies to every user who signed up with that code**, from their next deposit. Deposits already credited are not affected.
- **It applies only to stablecoins a user deposits from their own external wallet.** It does not apply to deposits into your pool, nor to charges from your pool to a user (`POST /pool/transfer`). The deduction on pool deposits is a separate rate (`feeRate` in `GET /pool/deposit_address`, see [Partner Pool](pool.md)).
- The fee is the deposited amount multiplied by the rate, rounded down to the cent.
- A rate below `0`, above `0.05`, or with more than 5 decimal places returns `400` and nothing is saved. A string must be a plain decimal starting with `0` (`"0.015"`; not `".015"` or `"1.5e-2"`).

## Errors

`400` bodies have the shape `{ "message": "...", "code": 400 }`. `<i>` is the zero-based index in `cardPrices`.

| `message` | Cause |
|---|---|
| `Invalid JSON body` | The body is not parseable JSON |
| `code must be 3-64 characters of letters, digits, hyphen or underscore` | `POST`: invalid `code` |
| ``only `enabled`, `cardPrices` and `depositFeeRate` can be updated; rename by deleting and creating a new code`` | `PATCH`: none of the three fields, or any other field, was sent |
| `cardPrices must be an array` | `cardPrices` is not an array (including `null` on `PATCH`) |
| `cardPrices accepts at most 20 entries` | More than 20 entries |
| `cardPrices[<i>] must be an object` | An entry is not an object |
| `cardPrices[<i>] has an unknown field: <field>` | An entry has a field other than `bin`, `type`, `price` |
| `cardPrices[<i>].bin must be a 6-8 digit string` | `bin` is not a string of 6–8 digits |
| `cardPrices[<i>].type must be "virtual" or "physical"` | Invalid `type` |
| `cardPrices[<i>].price must be a number with up to 2 decimal places` | `price` is not a non-negative number with up to 2 decimal places |
| `cardPrices has a duplicate entry for <bin> <type>` | Two entries for the same `bin` and `type` |
| `invalid amount for bin <bin>` | `price` is `0` or greater than `10000` |
| `bin <bin> has no default pricing for <type>` | That BIN is not offered with that `type` |
| `amount for bin <bin> is below the minimum chargeable price` | `price` is at or below the issuance cost of the card |
| `pricing rows unavailable for bin <bin>` | The price could not be checked at this moment. Retry |
| `depositFeeRate must be a decimal between 0 and 0.05 with up to 5 decimal places (e.g. "0.019"), or null` | Invalid `depositFeeRate` |

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

---
The machine-readable specification is [openapi.yaml](openapi.yaml). See also [Users](users.md) for reading the attributed users and their status.
