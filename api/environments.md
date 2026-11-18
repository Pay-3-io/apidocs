# Environments

Pay3 provides two independent environments: a sandbox for integration testing and production for live traffic.

## Base URLs

| Environment | Purpose | Base URL |
|---|---|---|
| **sandbox (Development)** | Integration testing against test cards and test identity verification. No real charges and no real cards. | `https://api-staging.pay-3.io/functions/v1/external-service` |
| **production** | Live traffic. | `https://api.pay-3.io/functions/v1/external-service` |

Both base URLs include the trailing `/external-service`. All API paths sit directly beneath the base URL, for example `GET {BASE_URL}/pool/balance`.

## Getting started in sandbox

1. Accept the invitation to the partner console for sandbox (`https://console-staging.pay-3.io`). In the **Developer** menu, look up your client ID, issue an API key, and register your source IPs.
2. Run the [Quickstart](quickstart.md) steps against the sandbox base URL.
3. Card issuance and identity verification run against sandbox providers, so nothing is charged and no real card is produced.

## Pool deposits

| Environment | Asset | Network |
|---|---|---|
| sandbox | USDC | Ethereum Sepolia (testnet) |
| production | USDT | TRON |

The deposit address, asset, and network are shown by `GET /pool/deposit_address` and in the console's **Pool** screen ([Pool](pool.md)). Sending any other asset or network to that address will not credit your pool. Each deposit must be at least 50.

## Sandbox limitations

The sandbox runs against the card provider's test environment, which behaves differently from production in a few places.

**Physical card shipping addresses.** The provider's sandbox has an incomplete postal-code dataset. A correct address in a country it does not cover — Vietnam, for example — is rejected at shipment registration with `Postal code and city do not match`. Production uses the full dataset, so the same address is accepted there.

- When testing physical cards in sandbox, use a shipping address in the **United States, the United Kingdom, or China**. For China, address line 1 must contain Chinese characters.
- Shipping fees depend on the destination country, so the amount charged in sandbox can differ from what the same user would pay for their real address.

**When shipment registration fails.** The card is created but not shipped. Until the shipment is registered:

- the card cannot be activated (setting the PIN returns an error), and
- new deposits by that user are held and do not appear in the card balance.

Contact Pay3 with the user's email or ID. We register the shipment again; the card does not need to be deleted or reissued.

**User deposits.** Sandbox accepts USDC on Ethereum Sepolia only. A deposit can take longer to be credited than in production.

## Suggested verification order

1. `oauth/access-token` — confirm authentication works.
2. `users/register` — create a user.
3. `kyc/access-token` → complete verification → `kyc/submit`.
4. `card/issue_card` with an `Idempotency-Key`.
5. `card/issuance_events` and `card/fetch_cards` — confirm the result.
6. Register a webhook endpoint in the console's **Developer** menu and use **Send test** to confirm delivery ([Webhooks](webhooks.md)).

## Notes

- Sandbox and production use **separate client credentials** (`pay3_sk_test_…` and `pay3_sk_live_…`). Do not mix them.
- Keep production credentials and webhook signing keys server-side only.

See also: [Authentication](authentication.md) · [openapi.yaml](openapi.yaml)
