--!strict
--[[
	SafeRemoteGateway
	Centralized server-side networking gateway providing:
	1. Typed runtime argument & nested dictionary validation (rejects NaN, Inf,
	   oversized strings, non-string table keys, mixed array/dict tables, deep nesting).
	2. Per-player token-bucket rate limiting with automatic PlayerRemoving cleanup.
	3. Clean RemoteEvent and UnreliableRemoteEvent registration + SimulateIncoming helper
	   for deterministic unit/Studio Edit-mode testing.
]]

export type FieldKind =
	"string"
	| "number"
	| "integer"
	| "boolean"
	| "Vector3"
	| "CFrame"
	| "Color3"
	| "Instance"
	| "table"

export type FieldSchema = {
	kind: FieldKind,
	optional: boolean?,
	min: number?,
	max: number?,
	maxLength: number?,
	className: string?,
	keys: { [string]: FieldSchema }?,
	allowExtraKeys: boolean?,
	maxDepth: number?,
}

export type RouteSchema = {
	args: { FieldSchema },
}

export type RateLimitConfig = {
	capacity: number,
	refillPerSecond: number,
}

export type DropCallback = (player: Player?, routeName: string, reason: string) -> ()

export type GatewayOptions = {
	onDrop: DropCallback?,
	clock: (() -> number)?,
}

export type RouteHandler = (player: Player, ...any) -> ()

type TokenBucket = {
	tokens: number,
	lastRefill: number,
}

type RegisteredRoute = {
	name: string,
	kind: "Reliable" | "Unreliable",
	remote: RemoteEvent | UnreliableRemoteEvent,
	schema: RouteSchema,
	rateLimit: RateLimitConfig,
	handler: RouteHandler,
	connection: RBXScriptConnection?,
	buckets: { [string]: TokenBucket },
}

local DEFAULT_MAX_STRING_LENGTH = 4096
local DEFAULT_MAX_TABLE_DEPTH = 3
local DEFAULT_MAX_TABLE_KEYS = 64

local SafeRemoteGateway = {}
SafeRemoteGateway.__index = SafeRemoteGateway

export type Gateway = typeof(setmetatable({} :: {
	_remotesFolder: Instance?,
	_routes: { [string]: RegisteredRoute },
	_connections: { RBXScriptConnection },
	_onDrop: DropCallback?,
	_clock: () -> number,
	_destroyed: boolean,
}, SafeRemoteGateway))

local function isFiniteNumber(n: number): boolean
	-- NaN fails self-equality; math.huge / -math.huge fail abs bound
	return n == n and math.abs(n) < math.huge
end

local function isFiniteVector3(v: Vector3): boolean
	return isFiniteNumber(v.X) and isFiniteNumber(v.Y) and isFiniteNumber(v.Z)
end

local function isFiniteCFrame(cf: CFrame): boolean
	local pos = cf.Position
	local right = cf.RightVector
	local up = cf.UpVector
	return isFiniteVector3(pos) and isFiniteVector3(right) and isFiniteVector3(up)
end

local function validateTableValue(tbl: { [any]: any }, schema: FieldSchema, depth: number, maxDepth: number): (boolean, string?)
	if depth > maxDepth then
		return false, `table depth exceeded limit ({maxDepth})`
	end

	local hasIntKey = false
	local hasStringKey = false
	local keyCount = 0
	local intCount = 0
	local maxIntKey = 0

	for k, v in tbl do
		keyCount += 1
		if keyCount > DEFAULT_MAX_TABLE_KEYS then
			return false, `table key count exceeded limit ({DEFAULT_MAX_TABLE_KEYS})`
		end

		local kType = typeof(k)
		if kType == "number" then
			if k < 1 or k % 1 ~= 0 then
				return false, "array index must be a positive integer"
			end
			hasIntKey = true
			intCount += 1
			if k > maxIntKey then
				maxIntKey = k
			end
		elseif kType == "string" then
			hasStringKey = true
		else
			return false, `unsupported table key type '{kType}'`
		end

		if hasIntKey and hasStringKey then
			return false, "mixed array and dictionary keys are rejected by remote serialization rules"
		end

		if kType == "string" and schema.keys then
			local fieldSpec = schema.keys[k]
			if not fieldSpec then
				if not schema.allowExtraKeys then
					return false, `unexpected table key '{k}'`
				end
			end
		end

		-- Recurse on explicit key schema or nested tables to enforce depth and table-shape hygiene
		if schema.keys and kType == "string" and schema.keys[k] then
			local ok, err = SafeRemoteGateway.ValidateField(schema.keys[k], v, depth + 1, maxDepth)
			if not ok then
				return false, `key '{k}': {err}`
			end
		elseif typeof(v) == "table" then
			local subSchema: FieldSchema = { kind = "table", maxDepth = maxDepth }
			local ok, err = validateTableValue(v :: { [any]: any }, subSchema, depth + 1, maxDepth)
			if not ok then
				return false, `key '{k}': {err}`
			end
		end
	end

	if hasIntKey and intCount ~= maxIntKey then
		return false, "sparse array with nil holes is rejected by remote serialization rules"
	end

	-- Verify required keys when schema.keys is defined
	if schema.keys then
		for expectedKey, expectedSpec in schema.keys do
			if not expectedSpec.optional and tbl[expectedKey] == nil then
				return false, `missing required key '{expectedKey}'`
			end
		end
	end

	return true, nil
end

function SafeRemoteGateway.ValidateField(schema: FieldSchema, value: unknown, depth: number?, maxDepthOverride: number?): (boolean, string?)
	local currentDepth = depth or 1
	local maxDepth = maxDepthOverride or schema.maxDepth or DEFAULT_MAX_TABLE_DEPTH

	if value == nil then
		if schema.optional then
			return true, nil
		end
		return false, `expected '{schema.kind}', got nil`
	end

	local kind = schema.kind
	local actualType = typeof(value)

	if kind == "integer" then
		if actualType ~= "number" then
			return false, `expected integer, got {actualType}`
		end
		local num = value :: number
		if not isFiniteNumber(num) then
			return false, "non-finite number (NaN/Inf)"
		end
		if num % 1 ~= 0 then
			return false, "expected integer without fractional part"
		end
		if schema.min and num < schema.min then
			return false, `value {num} below min {schema.min}`
		end
		if schema.max and num > schema.max then
			return false, `value {num} above max {schema.max}`
		end
		return true, nil
	elseif kind == "number" then
		if actualType ~= "number" then
			return false, `expected number, got {actualType}`
		end
		local num = value :: number
		if not isFiniteNumber(num) then
			return false, "non-finite number (NaN/Inf)"
		end
		if schema.min and num < schema.min then
			return false, `value {num} below min {schema.min}`
		end
		if schema.max and num > schema.max then
			return false, `value {num} above max {schema.max}`
		end
		return true, nil
	elseif kind == "string" then
		if actualType ~= "string" then
			return false, `expected string, got {actualType}`
		end
		local str = value :: string
		local cap = schema.maxLength or DEFAULT_MAX_STRING_LENGTH
		if #str > cap then
			return false, `string byte length {#str} exceeds cap {cap}`
		end
		return true, nil
	elseif kind == "boolean" then
		if actualType ~= "boolean" then
			return false, `expected boolean, got {actualType}`
		end
		return true, nil
	elseif kind == "Vector3" then
		if actualType ~= "Vector3" then
			return false, `expected Vector3, got {actualType}`
		end
		if not isFiniteVector3(value :: Vector3) then
			return false, "non-finite Vector3 component"
		end
		return true, nil
	elseif kind == "CFrame" then
		if actualType ~= "CFrame" then
			return false, `expected CFrame, got {actualType}`
		end
		if not isFiniteCFrame(value :: CFrame) then
			return false, "non-finite CFrame component"
		end
		return true, nil
	elseif kind == "Color3" then
		if actualType ~= "Color3" then
			return false, `expected Color3, got {actualType}`
		end
		local col = value :: Color3
		if not (isFiniteNumber(col.R) and isFiniteNumber(col.G) and isFiniteNumber(col.B)) then
			return false, "non-finite Color3 component"
		end
		return true, nil
	elseif kind == "Instance" then
		if actualType ~= "Instance" then
			return false, `expected Instance, got {actualType}`
		end
		local inst = value :: Instance
		if inst.Parent == nil then
			return false, "rejected unparented Instance"
		end
		if schema.className and not inst:IsA(schema.className) then
			return false, `expected {schema.className}, got {inst.ClassName}`
		end
		return true, nil
	elseif kind == "table" then
		if actualType ~= "table" then
			return false, `expected table, got {actualType}`
		end
		return validateTableValue(value :: { [any]: any }, schema, currentDepth, maxDepth)
	end

	return false, `unknown schema kind '{kind}'`
end

function SafeRemoteGateway.ValidateArgs(schema: RouteSchema, ...: any): (boolean, string?)
	local argCount = select("#", ...)
	local expectedArgs = schema.args
	if argCount > #expectedArgs then
		return false, `too many arguments ({argCount} > {#expectedArgs})`
	end

	for i = 1, #expectedArgs do
		local val: unknown = if i <= argCount then select(i, ...) else nil
		local ok, reason = SafeRemoteGateway.ValidateField(expectedArgs[i], val)
		if not ok then
			return false, `arg #{i}: {reason}`
		end
	end

	return true, nil
end

function SafeRemoteGateway.Create(remotesFolder: Instance?, options: GatewayOptions?): Gateway
	local opts: GatewayOptions = options or {}
	local clockFn = opts.clock or os.clock
	local self = setmetatable({
		_remotesFolder = remotesFolder,
		_routes = {} :: { [string]: RegisteredRoute },
		_connections = {} :: { RBXScriptConnection },
		_onDrop = opts.onDrop,
		_clock = clockFn,
		_destroyed = false,
	}, SafeRemoteGateway)
	return self
end

local function playerBucketKey(playerOrKey: any): string
	if typeof(playerOrKey) == "Instance" and playerOrKey:IsA("Player") then
		return tostring(playerOrKey.UserId)
	elseif type(playerOrKey) == "table" and playerOrKey.UserId ~= nil then
		return tostring(playerOrKey.UserId)
	end
	return tostring(playerOrKey)
end

function SafeRemoteGateway.ConsumeRateLimit(self: Gateway, playerOrKey: any, routeName: string, nowOverride: number?): boolean
	local route = self._routes[routeName]
	if not route then
		return false
	end

	local now = nowOverride or self._clock()
	local key = playerBucketKey(playerOrKey)
	local limit = route.rateLimit
	local capacity = math.max(1, limit.capacity)
	local refillRate = math.max(0, limit.refillPerSecond)

	local bucket = route.buckets[key]
	if not bucket then
		bucket = {
			tokens = capacity,
			lastRefill = now,
		}
		route.buckets[key] = bucket
	else
		local elapsed = math.max(0, now - bucket.lastRefill)
		bucket.tokens = math.min(capacity, bucket.tokens + elapsed * refillRate)
		bucket.lastRefill = now
	end

	if bucket.tokens < 1 then
		return false
	end

	bucket.tokens -= 1
	return true
end

function SafeRemoteGateway._ensureRemote(self: Gateway, routeName: string, className: "RemoteEvent" | "UnreliableRemoteEvent"): RemoteEvent | UnreliableRemoteEvent
	assert(not self._destroyed, "SafeRemoteGateway has been destroyed")
	local parent = self._remotesFolder
	assert(parent ~= nil, "remotesFolder must be provided before registering routes")

	local existing = parent:FindFirstChild(routeName)
	if existing then
		assert(existing:IsA(className), `Existing remote '{routeName}' has class '{existing.ClassName}', expected '{className}'`)
		return existing :: RemoteEvent | UnreliableRemoteEvent
	end

	local remote = Instance.new(className)
	remote.Name = routeName
	remote.Parent = parent
	return remote :: RemoteEvent | UnreliableRemoteEvent
end

function SafeRemoteGateway._dispatch(self: Gateway, route: RegisteredRoute, player: any, ...: any): (boolean, string?)
	if self._destroyed then
		return false, "gateway destroyed"
	end

	if not self:ConsumeRateLimit(player, route.name) then
		if self._onDrop then
			self._onDrop(player :: Player?, route.name, "rate limit exceeded")
		end
		return false, "rate limit exceeded"
	end

	local valid, reason = SafeRemoteGateway.ValidateArgs(route.schema, ...)
	if not valid then
		if self._onDrop then
			self._onDrop(player :: Player?, route.name, reason or "validation failed")
		end
		return false, reason
	end

	route.handler(player :: Player, ...)
	return true, nil
end

function SafeRemoteGateway.RegisterReliable(
	self: Gateway,
	routeName: string,
	schema: RouteSchema,
	rateLimit: RateLimitConfig,
	handler: RouteHandler
): RemoteEvent
	assert(self._routes[routeName] == nil, `Route '{routeName}' already registered`)
	local remote = self:_ensureRemote(routeName, "RemoteEvent") :: RemoteEvent

	local route: RegisteredRoute = {
		name = routeName,
		kind = "Reliable",
		remote = remote,
		schema = schema,
		rateLimit = rateLimit,
		handler = handler,
		buckets = {},
		connection = nil,
	}

	local okConn, connOrErr = pcall(function()
		return remote.OnServerEvent:Connect(function(player: Player, ...: any)
			self:_dispatch(route, player, ...)
		end)
	end)
	if okConn and connOrErr ~= nil then
		route.connection = connOrErr
		table.insert(self._connections, connOrErr)
	end

	self._routes[routeName] = route
	return remote
end

function SafeRemoteGateway.RegisterUnreliable(
	self: Gateway,
	routeName: string,
	schema: RouteSchema,
	rateLimit: RateLimitConfig,
	handler: RouteHandler
): UnreliableRemoteEvent
	assert(self._routes[routeName] == nil, `Route '{routeName}' already registered`)
	local remote = self:_ensureRemote(routeName, "UnreliableRemoteEvent") :: UnreliableRemoteEvent

	local route: RegisteredRoute = {
		name = routeName,
		kind = "Unreliable",
		remote = remote,
		schema = schema,
		rateLimit = rateLimit,
		handler = handler,
		buckets = {},
		connection = nil,
	}

	local okConn, connOrErr = pcall(function()
		return remote.OnServerEvent:Connect(function(player: Player, ...: any)
			self:_dispatch(route, player, ...)
		end)
	end)
	if okConn and connOrErr ~= nil then
		route.connection = connOrErr
		table.insert(self._connections, connOrErr)
	end

	self._routes[routeName] = route
	return remote
end

function SafeRemoteGateway.SimulateIncoming(self: Gateway, routeName: string, mockPlayer: any, ...: any): (boolean, string?)
	local route = self._routes[routeName]
	if not route then
		return false, `unknown route '{routeName}'`
	end
	return self:_dispatch(route, mockPlayer, ...)
end

function SafeRemoteGateway.BindPlayerCleanup(self: Gateway, playersService: Players): RBXScriptConnection
	assert(not self._destroyed, "SafeRemoteGateway has been destroyed")
	local conn = playersService.PlayerRemoving:Connect(function(player: Player)
		local key = playerBucketKey(player)
		for _, route in self._routes do
			route.buckets[key] = nil
		end
	end)
	table.insert(self._connections, conn)
	return conn
end

function SafeRemoteGateway.Destroy(self: Gateway)
	if self._destroyed then
		return
	end
	self._destroyed = true
	for _, conn in self._connections do
		if conn.Connected then
			conn:Disconnect()
		end
	end
	table.clear(self._connections)
	for _, route in self._routes do
		table.clear(route.buckets)
	end
	table.clear(self._routes)
end

return SafeRemoteGateway
