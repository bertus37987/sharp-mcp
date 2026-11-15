--!strict
--[[
	DialogueAndInteraction
	Configures server-validated ProximityPrompts and branching NPC dialogue
	trees compatible with `NpcDialogGui` (`02_roblox_gui`).
]]

local CollectionService = game:GetService("CollectionService")

export type DialogueChoice = {
	text: string,
	nextNodeId: string?,
	grantQuestId: string?,
	requiredTag: string?,
}

export type DialogueNode = {
	nodeId: string,
	speakerName: string,
	speakerTitle: string?,
	bodyText: string,
	choices: { DialogueChoice },
}

export type DialogueTree = {
	npcId: string,
	rootNodeId: string,
	nodes: { [string]: DialogueNode },
}

local DEFAULT_TAG = "SharpDialoguePromptManaged"

local DialogueAndInteraction = {}

function DialogueAndInteraction.AttachInteractPrompt(
	targetPartOrModel: Instance,
	actionText: string,
	objectText: string,
	maxDistance: number?,
	holdDuration: number?,
	tag: string?
): ProximityPrompt
	local managedTag = tag or DEFAULT_TAG
	local existing = targetPartOrModel:FindFirstChild("SharpInteractPrompt")
	if existing and existing:IsA("ProximityPrompt") then
		existing:Destroy()
	end

	local prompt = Instance.new("ProximityPrompt")
	prompt.Name = "SharpInteractPrompt"
	prompt.ActionText = actionText
	prompt.ObjectText = objectText
	prompt.MaxActivationDistance = maxDistance or 10.0
	prompt.HoldDuration = holdDuration or 0.0
	prompt.RequiresLineOfSight = true
	prompt.KeyboardKeyCode = Enum.KeyCode.E
	prompt.GamepadKeyCode = Enum.KeyCode.ButtonX
	prompt.Exclusivity = Enum.ProximityPromptExclusivity.OnePerButton
	CollectionService:AddTag(prompt, managedTag)
	prompt.Parent = targetPartOrModel
	return prompt
end

function DialogueAndInteraction.ValidateServerPromptTrigger(
	prompt: ProximityPrompt,
	characterRootPosition: Vector3,
	promptWorldPosition: Vector3
): (boolean, string)
	if not prompt.Enabled then
		return false, "PROMPT_DISABLED"
	end
	local dist = (characterRootPosition - promptWorldPosition).Magnitude
	if dist > (prompt.MaxActivationDistance + 6.0) then
		return false, "OUT_OF_ACTIVATION_DISTANCE"
	end
	return true, "VALID_INTERACTION"
end

function DialogueAndInteraction.SelectDialogueChoice(
	tree: DialogueTree,
	currentNodeId: string,
	choiceIndex: number,
	playerTags: { [string]: boolean }?
): (boolean, DialogueNode?, string?, string)
	local node = tree.nodes[currentNodeId]
	if not node then
		return false, nil, nil, "NODE_NOT_FOUND"
	end
	local choice = node.choices[choiceIndex]
	if not choice then
		return false, nil, nil, "INVALID_CHOICE_INDEX"
	end
	if choice.requiredTag and (not playerTags or not playerTags[choice.requiredTag]) then
		return false, node, nil, "MISSING_REQUIRED_TAG_" .. choice.requiredTag
	end
	if not choice.nextNodeId or choice.nextNodeId == "" then
		return true, nil, choice.grantQuestId, "DIALOGUE_COMPLETE"
	end
	local nextNode = tree.nodes[choice.nextNodeId]
	if not nextNode then
		return false, nil, nil, "NEXT_NODE_MISSING"
	end
	return true, nextNode, choice.grantQuestId, "ADVANCED_TO_" .. choice.nextNodeId
end

function DialogueAndInteraction.Cleanup(tag: string?): number
	local targetTag = tag or DEFAULT_TAG
	local removed = 0
	for _, inst in ipairs(CollectionService:GetTagged(targetTag)) do
		if inst.Parent then
			inst:Destroy()
			removed += 1
		end
	end
	return removed
end

return DialogueAndInteraction
