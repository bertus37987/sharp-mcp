--!strict
--[[
	SceneBudgetOptimizer
	Audits and optimizes Workspace scene geometry for StreamingEnabled and
	frame-time budgets:
	- Disables CastShadow & CanTouch on small decorative parts (< smallPartThresholdStuds)
	- Sets ModelStreamingMode = Atomic on multi-part gameplay/prop Models
	- Reports unanchored parts, total BaseParts, and shadow-casting counts
]]

local Workspace = game:GetService("Workspace")

export type OptimizationConfig = {
	targetRoot: Instance?,
	smallPartDiagonalStuds: number?,
	disableCanTouchOnStaticProps: boolean?,
	enforceAtomicOnMultiPartModels: boolean?,
	dryRun: boolean?,
}

export type OptimizationReport = {
	totalBasePartsScanned: number,
	totalModelsScanned: number,
	shadowsDisabledCount: number,
	canTouchDisabledCount: number,
	atomicModelsConfiguredCount: number,
	unanchoredPartsCount: number,
	streamingEnabled: boolean,
}

local SceneBudgetOptimizer = {}

function SceneBudgetOptimizer.OptimizeScene(config: OptimizationConfig?): OptimizationReport
	local cfg: OptimizationConfig = config or {}
	local root = cfg.targetRoot or Workspace
	local smallThreshold = cfg.smallPartDiagonalStuds or 5.5
	local disableTouch = if cfg.disableCanTouchOnStaticProps == nil then true else cfg.disableCanTouchOnStaticProps
	local enforceAtomic = if cfg.enforceAtomicOnMultiPartModels == nil then true else cfg.enforceAtomicOnMultiPartModels
	local dryRun = if cfg.dryRun == nil then false else cfg.dryRun

	local totalParts = 0
	local totalModels = 0
	local shadowsDisabled = 0
	local touchDisabled = 0
	local atomicConfigured = 0
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
		elseif desc:IsA("Model") then
			totalModels += 1
			if enforceAtomic then
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
		end
	end

	return {
		totalBasePartsScanned = totalParts,
		totalModelsScanned = totalModels,
		shadowsDisabledCount = shadowsDisabled,
		canTouchDisabledCount = touchDisabled,
		atomicModelsConfiguredCount = atomicConfigured,
		unanchoredPartsCount = unanchoredCount,
		streamingEnabled = Workspace.StreamingEnabled,
	}
end

return SceneBudgetOptimizer
