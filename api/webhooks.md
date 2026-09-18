# Webhooks

Events that occur in Pay3, such as card issuance, are pushed to your endpoint, so you can stay in sync without polling.

## Configuration

The receiving endpoint and the signing key are managed under **Developer → Webhooks** in the partner console.

- The receiving endpoint (HTTPS) and an optional description.
- The events you subscribe to, chosen from [Event types](#event-types). All are selected by default, and `ping` is delivered regardless. Unsubscribed events are not delivered and do not appear in the delivery log.
- The signing key, issued with the endpoint. It can be revealed at any time in the console, and reissuing it invalidates the previous key immediately.

## Delivery format

Events are delivered as a `POST` with a JSON body to the registered URL.

| Header | Contents |
|---|---|
| `X-Pay3-Event` | Event type, for example `card.issued` |
| `X-Pay3-Delivery` | Delivery id (unchanged across retries) |
| `X-Pay3-Signature` | Signature (see below) |

```json
{
  "id": "<delivery-uuid>",
  "type": "card.issued",
  "created_at": "2026-09-15T01:50:00.000Z",
  "data": { "userId": "<uuid>", "cardId": "<uuid>", "cardType": "virtual", "issuedAt": "2026-09-15T01:50:00.000Z" }
}
```

`data` contains only the fields defined for that event type. Raw responses from the card platform or the identity verification provider are never relayed.

## Signature verification

`X-Pay3-Signature` is an HMAC-SHA256 (hex) over the raw body as received, keyed with the webhook secret. Verification is required; discard any request that fails it.

```js
import crypto from "node:crypto";

function verify(rawBody, signature, secret) {
  const expected = crypto.createHmac("sha256", secret).update(rawBody).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signature));
}
```

## Retries

- A `2xx` response counts as a successful delivery.
- `5xx`, a 10-second timeout, and connection failures are retried with exponential backoff, up to 6 times. Retries run on a 5-minute cycle, so arrival can be up to 5 minutes later than the table below.
- `4xx` responses are not retried, because resending the same payload would not change the outcome; the delivery is marked `failed` immediately. `408`, `425`, and `429` are the exceptions and are retried.

| Retry | 1st | 2nd | 3rd | 4th | 5th | 6th (last) |
|---|---|---|---|---|---|---|
| Wait since the previous failure | 30 s | 60 s | 2 min | 4 min | 8 min | 16 min |

The wait is 30 seconds × 2^(retry − 1), capped at 1 hour. After 6 failed retries the delivery is marked `failed` — at most 7 attempts including the first. Recover anything you missed from the API (`GET /pool/ledger`, `GET /pool/transfers`, `GET /users/list`).

Process deliveries idempotently, de-duplicating on the body's `id` (equal to `X-Pay3-Delivery`). A retry arrives with the same `id` and the same bytes. `created_at` is the time the underlying state changed, fixed at first dispatch, so it does not change on retry.

## Delivery status

| State | Meaning |
|---|---|
| `pending` | Waiting to be delivered (first attempt, or waiting for a retry) |
| `delivered` | A `2xx` was received |
| `failed` | Delivery was attempted and failed, and the retry limit (6) was reached |
| `skipped_no_endpoint` | No endpoint was registered, so delivery was never attempted |

`skipped_no_endpoint` is not a delivery failure. Only events that occur after an endpoint is registered are delivered; earlier events are recorded this way and are never re-sent, so read them back from the API.

## Event types

| Event | Emitted when | `data` fields |
|---|---|---|
| `user.registered` | A new user signs up through your referral link | `userId, email, name, partnerRefCode, registeredAt` |
| `user.kyc.updated` | The result of either verification stage changes | `userId, kycStatus, stage, stageStatus, updatedAt` |
| `card.issued` | A virtual card is issued | `userId, cardId, cardType, issuedAt` |
| `card.activated` | A physical card is activated | `userId, cardId, cardType, activatedAt` |
| `pool.deposit.credited` | A pool credit is applied | `referenceId, grossAmount, feeAmount, netAmount, available, currency, transactionHash, chain, sourceAddress, creditedAt` |
| `pool.transfer.completed` | A charge is applied | `transferId, userId, amount, settledAt` |
| `pool.transfer.failed` | A charge fails and the amount is returned | `transferId, userId, amount, reason, compensatedAt` |

**`user.registered`** fires only for browser sign-ups carrying `?ref=`; `POST /users/register` does not emit it, because its response already returns `userId`. `partnerRefCode` is the same value that `GET /users/list` returns as `referralCode` for that user, so the two can be compared directly.

**`user.kyc.updated`** covers two stages — first-line identity verification (`identity`) and the card issuer's own review (`card_issuer`) — and is sent whenever either changes. `stage` is the stage that changed and `stageStatus` its new status (`approved`, `rejected`, `pending`). `kycStatus` is the overall status, where `approved` means charge instructions and card issuance will pass (same rules as [Users](users.md)). When only the first stage is approved, `kycStatus` is still `pending`, so wait for the event where `kycStatus` becomes `approved`.

```json
{ "userId": "<uuid>", "kycStatus": "pending",  "stage": "identity",    "stageStatus": "approved", "updatedAt": "..." }
{ "userId": "<uuid>", "kycStatus": "approved", "stage": "card_issuer", "stageStatus": "approved", "updatedAt": "..." }
```

**`card.activated`** applies to physical cards only, so `cardType` is always `physical`. It fires on successful activation and not on re-activation. Virtual cards are usable as soon as they are issued and emit `card.issued` only.

**`pool.deposit.credited`** is not tied to a user, so there is no `data.userId`. `referenceId` is `<chain>:<transactionHash>`, the same value as `referenceId` on the `deposit` row in `GET /pool/ledger` ([Partner Pool](pool.md)). `available` is the pool balance immediately after the credit.

## Test delivery and redelivery

- **Send test** under Developer → Webhooks delivers a single `ping` event. Its arrival is visible in the delivery log on the same screen.
- Failed deliveries are retried automatically every 5 minutes, up to the retry limit above. For a manual redelivery, contact Pay3 with the delivery `id` from the log.

The machine-readable API reference is `openapi.yaml`.
