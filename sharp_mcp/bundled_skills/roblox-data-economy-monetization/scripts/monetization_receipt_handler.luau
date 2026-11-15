--!strict
--[[
	MonetizationReceiptHandler
	Idempotent MarketplaceService.ProcessReceipt processor complying with
	`rbx-process-receipt-misuse`:
	1. Deduplicates PurchaseId before granting rewards.
	2. Atomically persists the profile + PurchaseId to DataStore BEFORE returning
	   Enum.ProductPurchaseDecision.PurchaseGranted.
	3. Returns NotProcessedYet if profile is missing or DataStore save fails.
]]

export type ReceiptInfo = {
	PurchaseId: string,
	PlayerId: number,
	ProductId: number,
	CurrencySpent: number?,
}

export type ProductGrantFn<T> = (data: T, receipt: ReceiptInfo) -> boolean

local MonetizationReceiptHandler = {}

function MonetizationReceiptHandler.CreateProcessor<T>(
	profileManager: {
		GetActiveProfile: (userId: number) -> any,
		SaveProfile: (userId: number, releaseSessionLock: boolean?) -> (boolean, string),
	},
	productHandlers: { [number]: ProductGrantFn<T> }
)
	local processor = {}

	function processor.ProcessReceipt(receiptInfo: ReceiptInfo): (Enum.ProductPurchaseDecision, string)
		local profile = profileManager.GetActiveProfile(receiptInfo.PlayerId)
		if not profile then
			return Enum.ProductPurchaseDecision.NotProcessedYet, "PROFILE_NOT_LOADED"
		end

		-- 1. Idempotency check: was this PurchaseId already fulfilled and saved?
		for _, seenId in ipairs(profile.processedReceipts) do
			if seenId == receiptInfo.PurchaseId then
				return Enum.ProductPurchaseDecision.PurchaseGranted, "ALREADY_PROCESSED_IDEMPOTENT"
			end
		end

		local handler = productHandlers[receiptInfo.ProductId]
		if not handler then
			return Enum.ProductPurchaseDecision.NotProcessedYet, "UNKNOWN_PRODUCT_ID"
		end

		-- 2. Execute grant handler inside pcall
		local okGrant, grantedOrErr = pcall(handler, profile.data, receiptInfo)
		if not okGrant or not grantedOrErr then
			return Enum.ProductPurchaseDecision.NotProcessedYet, "GRANT_HANDLER_FAILED"
		end

		-- 3. Record PurchaseId and immediately flush to DataStore BEFORE returning PurchaseGranted
		table.insert(profile.processedReceipts, receiptInfo.PurchaseId)
		local okSave, saveStatus = profileManager.SaveProfile(receiptInfo.PlayerId, false)
		if not okSave then
			-- Roll back PurchaseId marker in memory so next retry can re-attempt cleanly
			if profile.processedReceipts[#profile.processedReceipts] == receiptInfo.PurchaseId then
				table.remove(profile.processedReceipts)
			end
			return Enum.ProductPurchaseDecision.NotProcessedYet, "SAVE_FAILED_" .. tostring(saveStatus)
		end

		return Enum.ProductPurchaseDecision.PurchaseGranted, "GRANTED_AND_PERSISTED"
	end

	return processor
end

return MonetizationReceiptHandler
