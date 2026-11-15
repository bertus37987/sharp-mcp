--!strict
--[[
	EconomyInventoryQuestService
	Server-authoritative player economy ledger (Coins, Gems, XP, Level),
	stackable & unique inventory items, Shop catalog validator, Quest tracker,
	Promo-Code redeemer, leaderstats synchronizer, and pity-backed weighted loot roller.
]]

export type PlayerEconomyData = {
	Currencies: { [string]: number },
	Level: number,
	XP: number,
	Inventory: { [string]: number },
	EquippedItems: { [string]: string },
	Quests: { [string]: { progress: number, target: number, claimed: boolean } },
	RedeemedCodes: { [string]: boolean },
	LootPityCounter: number,
}

export type ShopItemSpec = {
	itemId: string,
	displayName: string,
	currency: string,
	price: number,
	maxStack: number?,
}

export type LootDropSpec = {
	itemId: string,
	rarity: "Common" | "Rare" | "Epic" | "Legendary",
	weight: number,
}

local EconomyInventoryQuestService = {}

function EconomyInventoryQuestService.CreateDefaultData(): PlayerEconomyData
	return {
		Currencies = {
			Coins = 250,
			Gems = 25,
		},
		Level = 1,
		XP = 0,
		Inventory = {
			StarterSword = 1,
			HealthPotion = 3,
		},
		EquippedItems = {
			PrimaryWeapon = "StarterSword",
		},
		Quests = {
			DefeatBandits = { progress = 0, target = 5, claimed = false },
			CollectRelics = { progress = 0, target = 3, claimed = false },
		},
		RedeemedCodes = {},
		LootPityCounter = 0,
	}
end

function EconomyInventoryQuestService.AddCurrency(
	data: PlayerEconomyData,
	currencyName: string,
	amount: number
): (boolean, number)
	if amount ~= amount or math.abs(amount) == math.huge then
		return false, data.Currencies[currencyName] or 0
	end
	local cur = data.Currencies[currencyName] or 0
	local nextVal = cur + math.floor(amount)
	if nextVal < 0 then
		return false, cur
	end
	data.Currencies[currencyName] = nextVal
	return true, nextVal
end

function EconomyInventoryQuestService.AddXP(data: PlayerEconomyData, xpGain: number): (number, number, boolean)
	if xpGain <= 0 then
		return data.Level, data.XP, false
	end
	data.XP += math.floor(xpGain)
	local leveledUp = false
	while true do
		local xpNeeded = data.Level * 100
		if data.XP >= xpNeeded then
			data.XP -= xpNeeded
			data.Level += 1
			leveledUp = true
		else
			break
		end
	end
	return data.Level, data.XP, leveledUp
end

function EconomyInventoryQuestService.PurchaseShopItem(
	data: PlayerEconomyData,
	item: ShopItemSpec,
	quantity: number?
): (boolean, string)
	local qty = math.max(1, math.floor(quantity or 1))
	local totalCost = item.price * qty
	local currentBal = data.Currencies[item.currency] or 0
	if currentBal < totalCost then
		return false, "INSUFFICIENT_FUNDS"
	end

	local currentStack = data.Inventory[item.itemId] or 0
	local maxStack = item.maxStack or 999
	if currentStack + qty > maxStack then
		return false, "MAX_STACK_EXCEEDED"
	end

	data.Currencies[item.currency] = currentBal - totalCost
	data.Inventory[item.itemId] = currentStack + qty
	return true, "PURCHASE_SUCCESS"
end

function EconomyInventoryQuestService.AdvanceQuest(
	data: PlayerEconomyData,
	questId: string,
	delta: number,
	rewardCurrency: string?,
	rewardAmount: number?
): (boolean, string)
	local q = data.Quests[questId]
	if not q then
		return false, "QUEST_NOT_FOUND"
	end
	if q.claimed then
		return false, "ALREADY_CLAIMED"
	end
	q.progress = math.min(q.target, q.progress + math.max(0, math.floor(delta)))
	if q.progress >= q.target then
		q.claimed = true
		local cur = rewardCurrency or "Coins"
		local amt = rewardAmount or 150
		EconomyInventoryQuestService.AddCurrency(data, cur, amt)
		return true, "QUEST_COMPLETED_AND_REWARDED"
	end
	return true, "QUEST_PROGRESS_UPDATED"
end

function EconomyInventoryQuestService.RedeemPromoCode(
	data: PlayerEconomyData,
	code: string,
	codeCatalog: { [string]: { currency: string, amount: number } }
): (boolean, string)
	local normalized = string.upper(string.gsub(code, "%s+", ""))
	if data.RedeemedCodes[normalized] then
		return false, "CODE_ALREADY_REDEEMED"
	end
	local reward = codeCatalog[normalized]
	if not reward then
		return false, "INVALID_CODE"
	end
	data.RedeemedCodes[normalized] = true
	EconomyInventoryQuestService.AddCurrency(data, reward.currency, reward.amount)
	return true, "CODE_REDEEMED"
end

function EconomyInventoryQuestService.RollWeightedLoot(
	data: PlayerEconomyData,
	lootTable: { LootDropSpec },
	pityThreshold: number?,
	rng: Random?
): LootDropSpec
	assert(#lootTable > 0, "Loot table must contain at least 1 entry.")
	local pityLimit = pityThreshold or 20
	data.LootPityCounter += 1

	if data.LootPityCounter >= pityLimit then
		for _, entry in ipairs(lootTable) do
			if entry.rarity == "Legendary" then
				data.LootPityCounter = 0
				data.Inventory[entry.itemId] = (data.Inventory[entry.itemId] or 0) + 1
				return entry
			end
		end
	end

	local totalWeight = 0
	for _, entry in ipairs(lootTable) do
		totalWeight += math.max(1, entry.weight)
	end

	local randomGen = rng or Random.new()
	local roll = randomGen:NextInteger(1, totalWeight)
	local cursor = 0
	local chosen = lootTable[1]
	for _, entry in ipairs(lootTable) do
		cursor += math.max(1, entry.weight)
		if roll <= cursor then
			chosen = entry
			break
		end
	end

	if chosen.rarity == "Legendary" then
		data.LootPityCounter = 0
	end
	data.Inventory[chosen.itemId] = (data.Inventory[chosen.itemId] or 0) + 1
	return chosen
end

function EconomyInventoryQuestService.SyncLeaderstats(player: Instance, data: PlayerEconomyData): Folder
	local existing = player:FindFirstChild("leaderstats")
	local folder: Folder
	if existing and existing:IsA("Folder") then
		folder = existing
	else
		if existing then
			existing:Destroy()
		end
		folder = Instance.new("Folder")
		folder.Name = "leaderstats"
		folder.Parent = player
	end

	local function setIntStat(statName: string, val: number)
		local iv = folder:FindFirstChild(statName)
		if not iv or not iv:IsA("IntValue") then
			if iv then
				iv:Destroy()
			end
			iv = Instance.new("IntValue")
			iv.Name = statName
			iv.Parent = folder
		end
		(iv :: IntValue).Value = math.floor(val)
	end

	setIntStat("Level", data.Level)
	setIntStat("Coins", data.Currencies.Coins or 0)
	setIntStat("Gems", data.Currencies.Gems or 0)
	return folder
end

return EconomyInventoryQuestService
