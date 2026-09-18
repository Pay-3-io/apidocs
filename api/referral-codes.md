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
| `referrals:read` | Listing codes |
| `referrals:write` | Creating, enabling, disabling and deleting codes (includes `referrals:read`) |

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
        "createdAt": "...", "updatedAt": "..." }
    ]
  }
  ```
- `link` is the sign-up link carrying the code: `https://app2.pay-3.io/?ref=<code>` in sandbox, `https://app.pay-3.io/?ref=<code>` in production.
- **No query parameters are accepted.** Any parameter returns `400` with a body such as `Unknown query parameter "enabled". Accepted: (none)`, so a filter that looks applied but is not can never be mistaken for a complete list. There is no paging and no filtering.

## POST /referral-codes

- body: `{ "code": "PARTNER-A", "label": "Agency A", "enabled": true }`
  - `label` and `enabled` are optional; `enabled` defaults to `true`. `label` is a free-form note for your own use and is not shown to end users.
- 201: the single code, in the shape above.
- 400: invalid code format.
- 409: the code is already taken, by you or by another partner.

## PATCH /referral-codes/{code}

Enables or disables a code; `enabled` is the only mutable field.

- body: `{ "enabled": false }`
- 200: the updated code.
- 400: an attempt to change anything other than `enabled` (renaming means delete, then create).
- 404: no such code for your client.

A disabled code stops attributing new sign-ups — `POST /users/register` returns `400` for it. **Users already attributed keep their attribution.**

## DELETE /referral-codes/{code}

- 200: `{ "code": "PARTNER-A", "deleted": true }`
- 404: no such code for your client.

Attribution is fixed at sign-up, so deleting a code changes neither past attribution nor reporting. Deletion cannot be undone.

Codes are matched exactly, case-insensitively. Wildcard characters carry no meaning in the path: `%` and `_` are not expanded, so bulk deletion is not possible.

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
