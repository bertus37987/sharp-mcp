--!strict
--[[
	DockWidget
	Builds and manages the Sharp MCP Companion DockWidgetPluginGui in Roblox Studio.
	Provides:
	- Connection status badge (127.0.0.1:<port> + HttpService.HttpEnabled status)
	- Copyable HttpService onboarding banner when HttpService.HttpEnabled == false
	- 3-Tier Safety Mode selector (Read-Only / Safe Mutate / Full + Upload)
	- Quick Undo button + 20-item live command execution feed
]]

local ChangeHistoryService = game:GetService("ChangeHistoryService")

export type SafetyMode = "Read-Only" | "Safe Mutate" | "Full + Upload"

local ONBOARDING_CMD = 'game:GetService("HttpService").HttpEnabled = true'

local DockWidget = {}
DockWidget.__index = DockWidget

function DockWidget.new(pluginObj: Plugin, port: number?)
	local self = setmetatable({}, DockWidget)
	local activePort = port or 58421
	self._plugin = pluginObj
	self._port = activePort
	self.safetyMode = (pluginObj:GetSetting("SharpSafetyMode") or "Safe Mutate") :: SafetyMode
	self._logs = {} :: { string }

	local toolbar = pluginObj:CreateToolbar("Sharp MCP")
	self._button = toolbar:CreateButton(
		"SharpCompanionToggle",
		"Open Sharp MCP Companion Panel",
		"rbxassetid://4458901886",
		"Sharp MCP"
	)

	local info = DockWidgetPluginGuiInfo.new(
		Enum.InitialDockState.Right,
		false,
		false,
		330,
		460,
		260,
		320
	)
	local widget = pluginObj:CreateDockWidgetPluginGuiAsync("SharpCompanionWidget", info)
	widget.Title = string.format("Sharp MCP (%d)", activePort)
	self._widget = widget

	local root = Instance.new("Frame")
	root.Name = "Root"
	root.Size = UDim2.fromScale(1, 1)
	root.BackgroundColor3 = Color3.fromRGB(22, 24, 32)
	root.BorderSizePixel = 0
	root.Parent = widget

	local pad = Instance.new("UIPadding")
	pad.PaddingTop = UDim.new(0, 10)
	pad.PaddingBottom = UDim.new(0, 10)
	pad.PaddingLeft = UDim.new(0, 10)
	pad.PaddingRight = UDim.new(0, 10)
	pad.Parent = root

	local layout = Instance.new("UIListLayout")
	layout.SortOrder = Enum.SortOrder.LayoutOrder
	layout.Padding = UDim.new(0, 8)
	layout.Parent = root

	local statusLbl = Instance.new("TextLabel")
	statusLbl.Name = "StatusLabel"
	statusLbl.LayoutOrder = 1
	statusLbl.Size = UDim2.new(1, 0, 0, 28)
	statusLbl.BackgroundColor3 = Color3.fromRGB(34, 38, 52)
	statusLbl.TextColor3 = Color3.fromRGB(230, 235, 245)
	statusLbl.Font = Enum.Font.GothamBold
	statusLbl.TextSize = 13
	statusLbl.Text = string.format("Status: Connecting (127.0.0.1:%d)...", activePort)
	statusLbl.Parent = root
	self._statusLbl = statusLbl

	local onboardingFrame = Instance.new("Frame")
	onboardingFrame.Name = "HttpOnboardingFrame"
	onboardingFrame.LayoutOrder = 2
	onboardingFrame.Size = UDim2.new(1, 0, 0, 84)
	onboardingFrame.BackgroundColor3 = Color3.fromRGB(64, 42, 24)
	onboardingFrame.BorderSizePixel = 0
	onboardingFrame.Visible = false
	onboardingFrame.Parent = root
	self._onboardingFrame = onboardingFrame

	local onboardPad = Instance.new("UIPadding")
	onboardPad.PaddingTop = UDim.new(0, 6)
	onboardPad.PaddingBottom = UDim.new(0, 6)
	onboardPad.PaddingLeft = UDim.new(0, 8)
	onboardPad.PaddingRight = UDim.new(0, 8)
	onboardPad.Parent = onboardingFrame

	local onboardTitle = Instance.new("TextLabel")
	onboardTitle.Name = "OnboardingNotice"
	onboardTitle.Size = UDim2.new(1, 0, 0, 28)
	onboardTitle.BackgroundTransparency = 1
	onboardTitle.TextColor3 = Color3.fromRGB(255, 224, 166)
	onboardTitle.Font = Enum.Font.GothamBold
	onboardTitle.TextSize = 11
	onboardTitle.TextXAlignment = Enum.TextXAlignment.Left
	onboardTitle.TextWrapped = true
	onboardTitle.Text = "HttpService is OFF. Copy & run in Studio Command Bar:"
	onboardTitle.Parent = onboardingFrame

	local cmdBox = Instance.new("TextBox")
	cmdBox.Name = "HttpCommandTextBox"
	cmdBox.Position = UDim2.new(0, 0, 0, 32)
	cmdBox.Size = UDim2.new(1, 0, 0, 38)
	cmdBox.BackgroundColor3 = Color3.fromRGB(20, 22, 30)
	cmdBox.TextColor3 = Color3.fromRGB(160, 240, 190)
	cmdBox.Font = Enum.Font.Code
	cmdBox.TextSize = 11
	cmdBox.TextXAlignment = Enum.TextXAlignment.Left
	cmdBox.TextWrapped = true
	cmdBox.ClearTextOnFocus = false
	cmdBox.TextEditable = false
	cmdBox.Text = ONBOARDING_CMD
	cmdBox.Parent = onboardingFrame
	self._cmdBox = cmdBox

	local modeBtn = Instance.new("TextButton")
	modeBtn.Name = "SafetyModeButton"
	modeBtn.LayoutOrder = 3
	modeBtn.Size = UDim2.new(1, 0, 0, 30)
	modeBtn.BackgroundColor3 = Color3.fromRGB(45, 110, 75)
	modeBtn.TextColor3 = Color3.fromRGB(255, 255, 255)
	modeBtn.Font = Enum.Font.GothamBold
	modeBtn.TextSize = 13
	modeBtn.Text = "Safety Mode: " .. self.safetyMode
	modeBtn.Parent = root
	self._modeBtn = modeBtn

	modeBtn.Activated:Connect(function()
		if self.safetyMode == "Read-Only" then
			self.safetyMode = "Safe Mutate"
		elseif self.safetyMode == "Safe Mutate" then
			self.safetyMode = "Full + Upload"
		else
			self.safetyMode = "Read-Only"
		end
		pluginObj:SetSetting("SharpSafetyMode", self.safetyMode)
		modeBtn.Text = "Safety Mode: " .. self.safetyMode
	end)

	local undoBtn = Instance.new("TextButton")
	undoBtn.Name = "UndoButton"
	undoBtn.LayoutOrder = 4
	undoBtn.Size = UDim2.new(1, 0, 0, 28)
	undoBtn.BackgroundColor3 = Color3.fromRGB(55, 62, 82)
	undoBtn.TextColor3 = Color3.fromRGB(240, 240, 250)
	undoBtn.Font = Enum.Font.GothamMedium
	undoBtn.TextSize = 12
	undoBtn.Text = "Undo Last Sharp Action"
	undoBtn.Parent = root
	undoBtn.Activated:Connect(function()
		pcall(function()
			ChangeHistoryService:Undo()
		end)
	end)

	local logBox = Instance.new("TextLabel")
	logBox.Name = "ActionLog"
	logBox.LayoutOrder = 5
	logBox.Size = UDim2.new(1, 0, 1, -112)
	logBox.BackgroundColor3 = Color3.fromRGB(16, 18, 24)
	logBox.TextColor3 = Color3.fromRGB(190, 200, 215)
	logBox.Font = Enum.Font.Code
	logBox.TextSize = 11
	logBox.TextXAlignment = Enum.TextXAlignment.Left
	logBox.TextYAlignment = Enum.TextYAlignment.Top
	logBox.TextWrapped = true
	logBox.Text = "Sharp Companion ready."
	logBox.Parent = root
	self._logBox = logBox

	self._button.Click:Connect(function()
		widget.Enabled = not widget.Enabled
	end)

	return self
end

function DockWidget:setHttpOnboarding(httpEnabled: boolean)
	if self._onboardingFrame then
		self._onboardingFrame.Visible = not httpEnabled
	end
	if self._cmdBox and not httpEnabled then
		self._cmdBox.Text = ONBOARDING_CMD
	end
	if self._logBox then
		local reserved = if httpEnabled then 112 else 204
		self._logBox.Size = UDim2.new(1, 0, 1, -reserved)
	end
end

function DockWidget:showIfNeeded(autoShow: boolean)
	if autoShow and self._widget then
		self._widget.Enabled = true
	end
end

function DockWidget:setStatus(text: string)
	if self._statusLbl then
		self._statusLbl.Text = text
	end
end

function DockWidget:appendLog(entry: string)
	table.insert(self._logs, 1, os.date("%H:%M:%S") .. " " .. entry)
	while #self._logs > 20 do
		table.remove(self._logs)
	end
	if self._logBox then
		self._logBox.Text = table.concat(self._logs, "\n")
	end
end

function DockWidget:destroy()
	if self._widget then
		self._widget:Destroy()
	end
end

return DockWidget
