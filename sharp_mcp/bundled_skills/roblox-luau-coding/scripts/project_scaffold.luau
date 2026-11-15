--!strict
--[[
	ProjectScaffold
	Idempotently creates and cleans up canonical Studio Explorer folders across
	standard Roblox services. Supports an isolated `rootPrefix` and `CollectionService`
	tag so tests and automated workflows never collide with existing place hierarchy.
]]

local CollectionService = game:GetService("CollectionService")

export type FolderNode = {
	name: string,
	children: { FolderNode }?,
}

export type ServiceLayout = {
	serviceName: string,
	folders: { FolderNode },
}

export type ScaffoldOptions = {
	rootPrefix: string?,
	tag: string?,
	services: { [string]: Instance }?,
	includeWorkspaceSubfolders: boolean?,
}

export type ScaffoldReport = {
	tag: string,
	rootPrefix: string,
	created: { string },
	existing: { string },
	totalManaged: number,
}

export type CleanupReport = {
	tag: string,
	rootPrefix: string,
	removed: { string },
	remainingCount: number,
}

local DEFAULT_TAG = "RobloxLuauCodingScaffold"
local MANAGED_ATTR = "LuauSkillScaffoldManaged"

local CANONICAL_LAYOUT: { ServiceLayout } = {
	{
		serviceName = "ReplicatedFirst",
		folders = {
			{ name = "Loading" },
		},
	},
	{
		serviceName = "ReplicatedStorage",
		folders = {
			{ name = "Shared", children = { { name = "Config" }, { name = "Types" }, { name = "Util" } } },
			{ name = "Remotes" },
			{ name = "Inputs" },
			{ name = "Assets" },
		},
	},
	{
		serviceName = "ServerScriptService",
		folders = {
			{ name = "Services" },
			{ name = "Systems" },
			{ name = "Security" },
		},
	},
	{
		serviceName = "ServerStorage",
		folders = {
			{ name = "Maps" },
			{ name = "Prefabs" },
			{ name = "ServerModules" },
		},
	},
	{
		serviceName = "StarterGui",
		folders = {},
	},
	{
		serviceName = "StarterPack",
		folders = {},
	},
	{
		serviceName = "StarterPlayer",
		folders = {},
	},
	{
		serviceName = "SoundService",
		folders = {
			{ name = "SoundGroups" },
		},
	},
	{
		serviceName = "Workspace",
		folders = {
			{ name = "World" },
			{ name = "NPCs" },
			{ name = "Interactables" },
		},
	},
}

local ProjectScaffold = {}

local function resolveService(serviceName: string, overrides: { [string]: Instance }?): Instance?
	if overrides and overrides[serviceName] then
		return overrides[serviceName]
	end
	local ok, svc = pcall(function()
		return game:GetService(serviceName)
	end)
	if ok then
		return svc
	end
	return nil
end

local function ensureFolder(parent: Instance, folderName: string, tag: string, report: ScaffoldReport): Folder
	local existing = parent:FindFirstChild(folderName)
	if existing and existing:IsA("Folder") then
		if tag ~= "" and not CollectionService:HasTag(existing, tag) then
			CollectionService:AddTag(existing, tag)
		end
		existing:SetAttribute(MANAGED_ATTR, true)
		table.insert(report.existing, existing:GetFullName())
		return existing
	end

	local folder = Instance.new("Folder")
	folder.Name = folderName
	folder:SetAttribute(MANAGED_ATTR, true)
	if tag ~= "" then
		CollectionService:AddTag(folder, tag)
	end
	folder.Parent = parent
	table.insert(report.created, folder:GetFullName())
	return folder
end

local function createTree(parent: Instance, nodes: { FolderNode }, tag: string, report: ScaffoldReport)
	for _, node in nodes do
		local folder = ensureFolder(parent, node.name, tag, report)
		if node.children then
			createTree(folder, node.children, tag, report)
		end
	end
end

function ProjectScaffold.GetCanonicalLayout(): { ServiceLayout }
	return CANONICAL_LAYOUT
end

function ProjectScaffold.Apply(options: ScaffoldOptions?): ScaffoldReport
	local opts: ScaffoldOptions = options or {}
	local rootPrefix = opts.rootPrefix or ""
	local tag = opts.tag or DEFAULT_TAG
	local includeWorkspace = if opts.includeWorkspaceSubfolders == nil then true else opts.includeWorkspaceSubfolders

	local report: ScaffoldReport = {
		tag = tag,
		rootPrefix = rootPrefix,
		created = {},
		existing = {},
		totalManaged = 0,
	}

	for _, layout in CANONICAL_LAYOUT do
		if layout.serviceName == "Workspace" and not includeWorkspace then
			continue
		end

		local service = resolveService(layout.serviceName, opts.services)
		if not service then
			continue
		end

		if layout.serviceName == "StarterPlayer" then
			local playerScripts = service:FindFirstChild("StarterPlayerScripts")
			local charScripts = service:FindFirstChild("StarterCharacterScripts")
			if playerScripts then
				local targetRoot = if rootPrefix ~= ""
					then ensureFolder(playerScripts, rootPrefix, tag, report)
					else playerScripts
				ensureFolder(targetRoot, "Controllers", tag, report)
				ensureFolder(targetRoot, "Components", tag, report)
			end
			if charScripts and rootPrefix ~= "" then
				ensureFolder(charScripts, rootPrefix, tag, report)
			end
			continue
		end

		local rootParent: Instance = service
		if rootPrefix ~= "" then
			rootParent = ensureFolder(service, rootPrefix, tag, report)
		end

		createTree(rootParent, layout.folders, tag, report)
	end

	report.totalManaged = #report.created + #report.existing
	return report
end

function ProjectScaffold.Cleanup(options: ScaffoldOptions?): CleanupReport
	local opts: ScaffoldOptions = options or {}
	local rootPrefix = opts.rootPrefix or ""
	local tag = opts.tag or DEFAULT_TAG

	local report: CleanupReport = {
		tag = tag,
		rootPrefix = rootPrefix,
		removed = {},
		remainingCount = 0,
	}

	-- Remove scoped rootPrefix folders first when specified
	if rootPrefix ~= "" then
		local searchRoots: { Instance } = {}
		for _, layout in CANONICAL_LAYOUT do
			local svc = resolveService(layout.serviceName, opts.services)
			if svc then
				table.insert(searchRoots, svc)
				if layout.serviceName == "StarterPlayer" then
					local ps = svc:FindFirstChild("StarterPlayerScripts")
					local cs = svc:FindFirstChild("StarterCharacterScripts")
					if ps then
						table.insert(searchRoots, ps)
					end
					if cs then
						table.insert(searchRoots, cs)
					end
				end
			end
		end

		for _, parent in searchRoots do
			local target = parent:FindFirstChild(rootPrefix)
			if target and target:IsA("Folder") and target:GetAttribute(MANAGED_ATTR) == true then
				table.insert(report.removed, target:GetFullName())
				target:Destroy()
			end
		end
	end

	-- Remove any remaining instances tagged with `tag` and marked managed
	if tag ~= "" then
		local tagged = CollectionService:GetTagged(tag)
		for _, inst in tagged do
			if inst.Parent ~= nil and inst:GetAttribute(MANAGED_ATTR) == true then
				if rootPrefix == "" or string.find(inst:GetFullName(), rootPrefix, 1, true) ~= nil then
					table.insert(report.removed, inst:GetFullName())
					inst:Destroy()
				end
			end
		end

		for _, inst in CollectionService:GetTagged(tag) do
			if inst.Parent ~= nil and inst:GetAttribute(MANAGED_ATTR) == true then
				if rootPrefix == "" or string.find(inst:GetFullName(), rootPrefix, 1, true) ~= nil then
					report.remainingCount += 1
				end
			end
		end
	end

	return report
end

return ProjectScaffold
