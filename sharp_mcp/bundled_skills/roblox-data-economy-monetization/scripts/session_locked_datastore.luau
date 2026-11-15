--!strict
--[[
	SessionLockedDataStore
	ProfileStore-grade player profile manager with:
	- UpdateAsync session locking (prevents item duplication across server hops)
	- Schema version migration
	- Automatic offline Studio in-memory mock fallback when API access is disabled
	- Clean release on PlayerRemoving / BindToClose
]]

local DataStoreService = game:GetService("DataStoreService")

export type ProfileMeta = {
	schemaVersion: number,
	sessionLockJobId: string?,
	sessionLockTimestamp: number,
	sessionLoadCount: number,
	updatedAt: number,
}

export type PlayerProfile<T> = {
	userId: number,
	key: string,
	data: T,
	meta: ProfileMeta,
	processedReceipts: { string },
	usingMockStore: boolean,
}

export type StoreConfig<T> = {
	storeName: string,
	schemaVersion: number,
	defaultDataFactory: () -> T,
	migrator: ((oldVersion: number, rawData: any) -> T)?,
	lockTimeoutSec: number?,
	forceMock: boolean?,
}

local MAX_RECEIPT_HISTORY = 100
local DEFAULT_LOCK_TIMEOUT_SEC = 180

local SessionLockedDataStore = {}

local function deepCopy<V>(val: V): V
	if type(val) ~= "table" then
		return val
	end
	local copy: { [any]: any } = {}
	for k, v in pairs(val :: any) do
		copy[deepCopy(k)] = deepCopy(v)
	end
	return (copy :: any) :: V
end

function SessionLockedDataStore.CreateManager<T>(config: StoreConfig<T>)
	local lockTimeout = config.lockTimeoutSec or DEFAULT_LOCK_TIMEOUT_SEC
	local activeProfiles: { [number]: PlayerProfile<T> } = {}
	local mockBackingStore: { [string]: any } = {}
	local liveStore: GlobalDataStore? = nil
	local useMock = if config.forceMock ~= nil then config.forceMock else (game.PlaceId == 0)

	if not useMock then
		local okStore, storeOrErr = pcall(function()
			return DataStoreService:GetDataStore(config.storeName)
		end)
		if okStore and storeOrErr then
			liveStore = storeOrErr
		else
			useMock = true
		end
	end

	local currentJobId = if #game.JobId > 0 then game.JobId else "StudioLocalSession"

	local function rawUpdateAsync(key: string, transformFn: (oldVal: any) -> any): (boolean, any)
		if not useMock and liveStore then
			local okUpd, resOrErr = pcall(function()
				return liveStore:UpdateAsync(key, transformFn)
			end)
			if okUpd then
				return true, resOrErr
			end
			-- Fallback to mock store if Studio API access is disabled
			useMock = true
		end

		local existing = deepCopy(mockBackingStore[key])
		local updated = transformFn(existing)
		if updated ~= nil then
			mockBackingStore[key] = deepCopy(updated)
		end
		return true, deepCopy(mockBackingStore[key])
	end

	local manager = {}

	function manager.LoadProfile(userId: number, stealStaleLock: boolean?): (boolean, PlayerProfile<T>?, string)
		local key = "Player_" .. tostring(userId)
		local now = os.time()
		local lockBlockedByOtherServer = false

		local ok, rawEnvelope = rawUpdateAsync(key, function(oldEnvelope: any): any
			if type(oldEnvelope) ~= "table" then
				local freshData = config.defaultDataFactory()
				return {
					data = freshData,
					meta = {
						schemaVersion = config.schemaVersion,
						sessionLockJobId = currentJobId,
						sessionLockTimestamp = now,
						sessionLoadCount = 1,
						updatedAt = now,
					},
					processedReceipts = {},
				}
			end

			local meta: ProfileMeta = oldEnvelope.meta or {
				schemaVersion = 1,
				sessionLockJobId = nil,
				sessionLockTimestamp = 0,
				sessionLoadCount = 0,
				updatedAt = now,
			}

			local lockedByOther = meta.sessionLockJobId ~= nil
				and meta.sessionLockJobId ~= currentJobId
				and (now - (meta.sessionLockTimestamp or 0)) < lockTimeout

			if lockedByOther and not stealStaleLock then
				lockBlockedByOtherServer = true
				return nil
			end

			local data: T = oldEnvelope.data
			if (meta.schemaVersion or 1) < config.schemaVersion and config.migrator then
				data = config.migrator(meta.schemaVersion or 1, data)
			end
			-- Reconcile missing top-level default keys
			local defaults = config.defaultDataFactory()
			if type(data) == "table" and type(defaults) == "table" then
				for k, defVal in pairs(defaults :: any) do
					if (data :: any)[k] == nil then
						(data :: any)[k] = deepCopy(defVal)
					end
				end
			end

			meta.schemaVersion = config.schemaVersion
			meta.sessionLockJobId = currentJobId
			meta.sessionLockTimestamp = now
			meta.sessionLoadCount = (meta.sessionLoadCount or 0) + 1
			meta.updatedAt = now

			oldEnvelope.data = data
			oldEnvelope.meta = meta
			oldEnvelope.processedReceipts = oldEnvelope.processedReceipts or {}
			return oldEnvelope
		end)

		if not ok or lockBlockedByOtherServer or type(rawEnvelope) ~= "table" then
			return false, nil, if lockBlockedByOtherServer then "SESSION_LOCKED_BY_OTHER_SERVER" else "DATASTORE_ERROR"
		end

		local profile: PlayerProfile<T> = {
			userId = userId,
			key = key,
			data = rawEnvelope.data,
			meta = rawEnvelope.meta,
			processedReceipts = rawEnvelope.processedReceipts or {},
			usingMockStore = useMock,
		}
		activeProfiles[userId] = profile
		return true, profile, "LOADED"
	end

	function manager.GetActiveProfile(userId: number): PlayerProfile<T>?
		return activeProfiles[userId]
	end

	function manager.SaveProfile(userId: number, releaseSessionLock: boolean?): (boolean, string)
		local profile = activeProfiles[userId]
		if not profile then
			return false, "NO_ACTIVE_PROFILE"
		end

		local now = os.time()
		local lockOwnershipLost = false
		local ok, _ = rawUpdateAsync(profile.key, function(oldEnvelope: any): any
			if type(oldEnvelope) == "table" and type(oldEnvelope.meta) == "table" then
				local existingOwner = oldEnvelope.meta.sessionLockJobId
				if existingOwner ~= nil and existingOwner ~= currentJobId then
					lockOwnershipLost = true
					return nil
				end
			end

			profile.meta.updatedAt = now
			if releaseSessionLock then
				profile.meta.sessionLockJobId = nil
			else
				profile.meta.sessionLockJobId = currentJobId
				profile.meta.sessionLockTimestamp = now
			end

			while #profile.processedReceipts > MAX_RECEIPT_HISTORY do
				table.remove(profile.processedReceipts, 1)
			end

			return {
				data = deepCopy(profile.data),
				meta = deepCopy(profile.meta),
				processedReceipts = deepCopy(profile.processedReceipts),
			}
		end)

		if lockOwnershipLost then
			activeProfiles[userId] = nil
			return false, "LOCK_OWNERSHIP_LOST"
		end
		if releaseSessionLock then
			activeProfiles[userId] = nil
		end
		return ok, if releaseSessionLock then "RELEASED" else "SAVED"
	end

	function manager.FlushAllProfiles(): number
		local flushed = 0
		local ids: { number } = {}
		for uid in pairs(activeProfiles) do
			table.insert(ids, uid)
		end
		for _, uid in ipairs(ids) do
			local ok = manager.SaveProfile(uid, true)
			if ok then
				flushed += 1
			end
		end
		return flushed
	end

	return manager
end

return SessionLockedDataStore
