# Idempotency

Operations that move money or provision accounts are idempotent, so a network retry cannot execute them twice.

## Usage

Send an `Idempotency-Key` header. The value is a unique string you generate; a UUID is recommended.

```bash
curl -X POST "$BASE_URL/card/issue_card" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "Idempotency-Key: 7c1f...-unique" \
  -d '{ "userId": "<uuid>", "type": "virtual" }'
```

## Behavior

- Only the first request for a given `(client, Idempotency-Key, endpoint)` triple is executed, and its result is stored.
- A retry with the same key returns **the stored first result**, without re-executing. Two cards are never issued.
- That stored result is a replay, **not the current state**. For example, retrying `POST /pool/transfer` returns the original `{"status":"pending"}` even after the instruction has settled. This keeps "same key, same response" a firm contract. Read current state with `GET /pool/transfer/{transferId}`.
- Reusing a key with a **different body** returns `409`. This catches a key accidentally attached to a different instruction.
- Sending the same key while the first request is still in progress returns `409` (in progress). Wait briefly and retry.
- If the first request failed with a server error, the key is released and can be reused.

## Endpoints that support it

| Endpoint |
|---|
| `POST /card/issue_card` |
| `POST /kyc/submit` |
| `POST /pool/transfer` |

Requests without the header still work, but sending it on these operations is strongly recommended.

See also: [Quickstart](quickstart.md) · [openapi.yaml](openapi.yaml)
