--!strict
--[[
	SceneBudgetOptimizer
	Audits and optimizes Workspace scene geometry for StreamingEnabled and
	frame-time budgets:
	- Disables CastShadow, CanTouch & non-interactive CanQuery on small decorative parts
	- Sets Box CollisionFidelity & Automatic RenderFidelity on small decorative MeshParts/Unions
	- Sets ModelStreamingMode = Atomic on multi-part Models without nesting Persistent inside Atomic
	- Opts composite static Models >= 64 cubic studs into ModelLevelOfDetail.SLIM (pcall-guarded)
	- Reports unanchored parts, total BaseParts, SLIM candidates, and shadow-casting counts
]]

local Workspace = game:GetService("Workspace")

export type OptimizationConfig = {
	targetRoot: Instance?,
	smallPartDiagonalStuds: number?,
	disableCanTouchOnStaticProps: boolean?,
	disableCanQueryOnDecorProps: boolean?,
	enforceAtomicOnMultiPartModels: boolean?,
	enforceSlimOnCompositeModels: boolean?,
	dryRun: boolean?,
}

export type OptimizationReport = {
	totalBasePartsScanned: number,
	totalModelsScanned: number,
	shadowsDisabledCount: number,
	canTouchDisabledCount: number,
	canQueryDisabledCount: number,
	boxCollisionSetCount: number,
	renderFidelityAutoCount: number,
	atomicModelsConfiguredCount: number,
	slimModelsConfiguredCount: number,
	unanchoredPartsCount: number,
	streamingEnabled: boolean,
}

local SceneBudgetOptimizer = {}

local function hasAtomicAncestor(inst: Instance, stopRoot: Instance): boolean
	local cur = inst.Parent
	while cur and cur ~= stopRoot and cur ~= game do
		if cur:IsA("Model") then
			local ok, mode = pcall(function()
				return cur.ModelStreamingMode
			end)
			if ok and mode == Enum.ModelStreamingMode.Atomic then
				return true
			end
		end
		cur = cur.Parent
	end
	return false
end

function SceneBudgetOptimizer.OptimizeScene(config: OptimizationConfig?): OptimizationReport
	local cfg: OptimizationConfig = config or {}
	local root = cfg.targetRoot or Workspace
	local smallThreshold = cfg.smallPartDiagonalStuds or 5.5
	local disableTouch = if cfg.disableCanTouchOnStaticProps == nil then true else cfg.disableCanTouchOnStaticProps
	local disableQuery = if cfg.disableCanQueryOnDecorProps == nil then true else cfg.disableCanQueryOnDecorProps
	local enforceAtomic = if cfg.enforceAtomicOnMultiPartModels == nil then true else cfg.enforceAtomicOnMultiPartModels
	local enforceSlim = if cfg.enforceSlimOnCompositeModels == nil then true else cfg.enforceSlimOnCompositeModels
	local dryRun = if cfg.dryRun == nil then false else cfg.dryRun

	local totalParts = 0
	local totalModels = 0
	local shadowsDisabled = 0
	local touchDisabled = 0
	local queryDisabled = 0
	local boxCollisionSet = 0
	local renderFidelityAuto = 0
	local atomicConfigured = 0
	local slimConfigured = 0
	local unanchoredCount = 0

	for _, desc in ipairs(root:GetDescendants()) do
		if desc:IsA("BasePart") and not desc:IsA("Terrain") then
			totalParts += 1
			if not desc.Anchored then
				unanchoredCount += 1
			end
			if desc.Size.Magnitude <= smallThreshold and desc.CastShadow then
				shadowsDisabled += 1
				if not dryRun then
					desc.CastShadow = false
				end
			end
			if disableTouch and desc.Anchored and desc.CanTouch then
				touchDisabled += 1
				if not dryRun then
					desc.CanTouch = false
				end
			end
			if disableQuery and desc.Anchored and not desc.CanCollide and desc.CanQuery and desc.Size.Magnitude <= smallThreshold then
				if desc:FindFirstChildWhichIsA("ClickDetector") == nil and desc:FindFirstChildWhichIsA("ProximityPrompt") == nil then
					queryDisabled += 1
					if not dryRun then
						desc.CanQuery = false
					end
				end
			end
			if (desc:IsA("MeshPart") or desc:IsA("UnionOperation")) and desc.Anchored then
				if desc.Size.Magnitude <= smallThreshold then
					local okCol, curCol = pcall(function()
						return (desc :: any).CollisionFidelity
					end)
					if okCol and curCol ~= Enum.CollisionFidelity.Box then
						boxCollisionSet += 1
						if not dryRun then
							pcall(function()
								(desc :: any).CollisionFidelity = Enum.CollisionFidelity.Box
							end)
						end
					end
				end
				local okRen, curRen = pcall(function()
					return (desc :: any).RenderFidelity
				end)
				if okRen and curRen ~= Enum.RenderFidelity.Automatic then
					renderFidelityAuto += 1
					if not dryRun then
						pcall(function()
							(desc :: any).RenderFidelity = Enum.RenderFidelity.Automatic
						end)
					end
				end
			end
		elseif desc:IsA("Model") then
			totalModels += 1
			if enforceAtomic and not hasAtomicAncestor(desc, root) then
				local okMode, curMode = pcall(function()
					return desc.ModelStreamingMode
				end)
				if okMode and curMode == Enum.ModelStreamingMode.Default then
					atomicConfigured += 1
					if not dryRun then
						pcall(function()
							desc.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
						end)
					end
				end
			end
			if enforceSlim then
				local okBox, _, bSize = pcall(function()
					return desc:GetBoundingBox()
				end)
				if okBox and typeof(bSize) == "Vector3" and (bSize.X * bSize.Y * bSize.Z) >= 64 then
					local partCount = 0
					local allAnchored = true
					for _, child in ipairs(desc:GetDescendants()) do
						if child:IsA("BasePart") then
							partCount += 1
							if not child.Anchored then
								allAnchored = false
								break
							end
						end
					end
					if allAnchored and partCount >= 4 then
						local okLod, curLod = pcall(function()
							return (desc :: any).LevelOfDetail
						end)
						if okLod and tostring(curLod) ~= "Enum.ModelLevelOfDetail.SLIM" then
							slimConfigured += 1
							if not dryRun then
								pcall(function()
									(desc :: any).LevelOfDetail = Enum.ModelLevelOfDetail.SLIM
								end)
							end
						end
					end
				end
			end
		end
	end

	return {
		totalBasePartsScanned = totalParts,
		totalModelsScanned = totalModels,
		shadowsDisabledCount = shadowsDisabled,
		canTouchDisabledCount = touchDisabled,
		canQueryDisabledCount = queryDisabled,
		boxCollisionSetCount = boxCollisionSet,
		renderFidelityAutoCount = renderFidelityAuto,
		atomicModelsConfiguredCount = atomicConfigured,
		slimModelsConfiguredCount = slimConfigured,
		unanchoredPartsCount = unanchoredCount,
		streamingEnabled = Workspace.StreamingEnabled,
	}
end

return SceneBudgetOptimizer
