# DataStore Session-Locking, Economy Ledger & Idempotent Monetization Reference

## 1. DataStore Quotas & Payload Budgets

| Operation | Per-Server Quota | Key/Value Limit | Best Practice |
| :--- | :--- | :--- | :--- |
| `GetAsync` / `SetAsync` / `UpdateAsync` | `60 + (10 * Players)` requests/min | `4,194,304` chars (4 MB) per key; `64` chars key name | Auto-save every `120–180s` + on `PlayerRemoving` + immediate save on Robux `ProcessReceipt`. |
| Per-Key Write Cooldown | 6 seconds between writes to the *same* key | - | Coalesce rapid currency/XP changes in memory; flush on interval or disconnect. |

---

## 2. Anti-Dupe Session Lock State Machine

```text
[Player Joins Server B]
   │
   ▼
DataStore:UpdateAsync("Player_123", function(old)
   ├── If old.sessionLockJobId == nil OR old.sessionLockJobId == game.JobId OR (os.time() - old.sessionLockTime) >= 180:
   │      Claim lock (sessionLockJobId = game.JobId, sessionLockTime = os.time())
   └── Else:
          Keep waiting / retry (Server A is still flushing Player_123)
end)
```

---

## 3. Idempotent `MarketplaceService.ProcessReceipt` Checklist

1. **Never grant items without saving `receiptInfo.PurchaseId` first.** Roblox retries `ProcessReceipt` every time the player joins until a callback returns `Enum.ProductPurchaseDecision.PurchaseGranted`.
2. **Cap `ProcessedReceipts` history to ~100 entries** (FIFO queue) so the JSON array never bloats the 4 MB DataStore key limit.
3. **Never yield indefinitely** inside `ProcessReceipt` without returning `NotProcessedYet` on timeout/failure.
