---
name: roblox-data-economy-monetization
description: >-
  Build session-locked Roblox player DataStore profiles (UpdateAsync with
  anti-dupe session locking, schema migration, BindToClose flush, and automatic
  offline Studio mock fallback), server-authoritative currency/inventory/quest/loot
  ledgers wired to 02_roblox_gui modals, and idempotent MarketplaceService.ProcessReceipt
  monetization handlers. Use whenever the user asks for saving player data,
  DataStores, leaderstats, shops, inventories, quests, codes, loot tables,
  Developer Products, or GamePasses.
---

# Roblox Player Data, Economy, Quests & Monetization (`roblox-data-economy-monetization`)

Production architecture and `--!strict` server modules for **anti-dupe session-locked DataStores**, **server-authoritative Economy/Inventory/Quest/Loot ledgers** (wired directly to the `ModalMenusGui` from `roblox-gui`), and **idempotent `MarketplaceService.ProcessReceipt`** fulfillment.

---

## 1. Non-Negotiable Security & Persistence Guardrails

1. **`--!strict` & Server-Only Storage (`ServerScriptService` / `ServerStorage`):**
   - Never place DataStore, loot table, promo-code, or `ProcessReceipt` modules inside `ReplicatedStorage` (clients can decompile any replicated `ModuleScript`).
2. **Session-Locked `UpdateAsync` (Never Raw `SetAsync` for Player Profiles):**
   - Always load and save player profiles via `DataStore:UpdateAsync(key, transformFn)` checking `activeLockJobId` and `lockTimestamp` (expiring stale locks only after `>= 180` seconds) so rapid server-hopping cannot duplicate traded or spent items.
   - Always provide an automatic **In-Memory Studio Fallback** when `DataStoreService` throws `502` / `StudioAccessToApisNotAllowed` or when `game.PlaceId == 0`, so every Studio playtest works out-of-the-box with zero errors.
3. **Idempotent `MarketplaceService.ProcessReceipt` (`rbx-process-receipt-misuse`):**
   - There must be **exactly one** `MarketplaceService.ProcessReceipt` callback in the entire experience.
   - Inside `ProcessReceipt(receiptInfo)`:
     1. Check if `receiptInfo.PurchaseId` is already in `profile.ProcessedReceipts` (ring buffer of last 100 `PurchaseId`s); if so, immediately return `Enum.ProductPurchaseDecision.PurchaseGranted`.
     2. Grant the reward and append `receiptInfo.PurchaseId` to `profile.ProcessedReceipts`.
     3. Persist the profile via `UpdateAsync` **before** returning `PurchaseGranted`. If the DataStore write fails or the player left before profile load, return `Enum.ProductPurchaseDecision.NotProcessedYet`.
4. **Weighted Loot Tables & Pity Counter:**
   - Roll all loot and gacha drops exclusively on the server using integer weights (`totalWeight`) and deterministic pity thresholds (`guaranteedLegendaryEveryN`).

---

## 2. Canonical Scripts & References

### Scripts (`scripts/`)
- [`scripts/session_locked_datastore.luau`](scripts/session_locked_datastore.luau): `SessionLockedDataStore` — ProfileStore-grade `UpdateAsync` session locking, schema versioning/migration, `BindToClose` batch release, and automatic offline Studio mock storage.
- [`scripts/economy_inventory_quest_service.luau`](scripts/economy_inventory_quest_service.luau): `EconomyInventoryQuestService` — Server-authoritative currency ledger (`Coins`, `Gems`), stackable/unique inventory items, shop purchase validator, quest state machine, promo code redeemer, and pity-backed weighted loot roller, plus `leaderstats` sync.
- [`scripts/monetization_receipt_handler.luau`](scripts/monetization_receipt_handler.luau): `MonetizationReceiptHandler` — Idempotent `ProcessReceipt` router with atomic `PurchaseId` recording, `GamePass` ownership cache (`UserOwnsGamePassAsync`), and `AnalyticsService` economy hooks.

### References (`references/`)
- [`references/datastore_economy_and_monetization_patterns.md`](references/datastore_economy_and_monetization_patterns.md): DataStore rate limits (`60 + numPlayers * 10` RPM), 4 MB profile payload ceiling, session-lock state transitions, and `ProcessReceipt` edge-case matrix.

---

## 3. Execution Workflow via `Sharp` MCP

1. Call `sharp_data_economy_monetization(action="install", ...)` to install `SessionLockedDataStore`, `EconomyInventoryQuestService`, and `MonetizationReceiptHandler` into `ServerScriptService`.
2. Call `sharp_data_economy_monetization(action="smoke_test")` to verify offline Studio mock fallback, quest/promo/pity loot rules, and idempotent `ProcessReceipt` replay protection.
