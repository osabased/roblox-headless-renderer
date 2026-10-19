--!strict
-- The gamepad, touch-control and input-state reads of GuiService and UserInputService,
-- one label per read (its value, or the error), in name order: TouchControlsSetOff
-- changes what the reads after it see.
local GuiService = game:GetService("GuiService")
local UserInputService = game:GetService("UserInputService")

local function show(value: any): string
	if typeof(value) == "table" then
		local parts = {}
		for _, item in value do
			table.insert(parts, show(item))
		end
		return `[{table.concat(parts, ",")}]`
	elseif typeof(value) == "Instance" then
		return value.Name
	elseif typeof(value) == "EnumItem" then
		return value.Name
	elseif typeof(value) == "Vector2" then
		return `{value.X},{value.Y}`
	end
	return tostring(value)
end

local gui: any = GuiService
local input: any = UserInputService
local pad1 = Enum.UserInputType.Gamepad1
local pad2 = Enum.UserInputType.Gamepad2

local reads: { [string]: () -> any } = {
	TouchControlsEnabled = function()
		return gui.TouchControlsEnabled
	end,
	TouchControlsSetOff = function()
		gui.TouchControlsEnabled = false
		return gui.TouchControlsEnabled
	end,
	IsTenFootInterface = function()
		return gui:IsTenFootInterface()
	end,
	GuiFlags = function()
		return `{gui.AutoSelectGuiEnabled} {gui.CoreGuiNavigationEnabled} {gui.GuiNavigationEnabled} {gui.IsModalDialog} {gui.MenuIsOpen}`
	end,
	IsWindows = function()
		return gui.IsWindows
	end,
	EmotesMenu = function()
		return `{gui:GetEmotesMenuOpen()} {gui:GetInspectMenuEnabled()}`
	end,
	GetConnectedGamepads = function()
		return input:GetConnectedGamepads()
	end,
	GetNavigationGamepads = function()
		return input:GetNavigationGamepads()
	end,
	GetGamepadConnected = function()
		return `{input:GetGamepadConnected(pad1)} {input:GetGamepadConnected(pad2)}`
	end,
	IsNavigationGamepad = function()
		return `{input:IsNavigationGamepad(pad1)} {input:IsNavigationGamepad(pad2)}`
	end,
	GetSupportedGamepadKeyCodes = function()
		local keys = input:GetSupportedGamepadKeyCodes(pad1)
		local others = input:GetSupportedGamepadKeyCodes(pad2)
		return `{#keys} {show(keys[1])} {show(keys[#keys])} {#others}`
	end,
	SensorFlags = function()
		return `{input.AccelerometerEnabled} {input.GyroscopeEnabled} {input.VREnabled} {input.ModalEnabled}`
	end,
	Mouse = function()
		return `{show(input.MouseBehavior)} {input.MouseDeltaSensitivity} [{input.MouseIcon}] {input.MouseIconEnabled}`
	end,
	MouseIconContent = function()
		return typeof(input.MouseIconContent)
	end,
	OnScreenKeyboard = function()
		return `{input.OnScreenKeyboardVisible} {show(input.OnScreenKeyboardPosition)} {show(input.OnScreenKeyboardSize)}`
	end,
	UserHeadCFrame = function()
		return `{input.UserHeadCFrame == CFrame.identity} {input:GetUserCFrame(Enum.UserCFrame.Head) == CFrame.identity}`
	end,
	Pressed = function()
		return `{input:IsKeyDown(Enum.KeyCode.E)} {input:IsMouseButtonPressed(Enum.UserInputType.MouseButton1)} {input:IsGamepadButtonDown(pad1, Enum.KeyCode.ButtonA)}`
	end,
	Held = function()
		return `{show(input:GetKeysPressed())} {show(input:GetMouseButtonsPressed())} {show(input:GetMouseDelta())} {input:GetFocusedTextBox()}`
	end,
	GetStringForKeyCode = function()
		local keys = { "E", "One", "Space", "Hash", "BackSlash", "ButtonA", "DPadUp", "Return", "F1" }
		local parts = {}
		for _, key in keys do
			table.insert(parts, `{key}=[{input:GetStringForKeyCode(Enum.KeyCode[key])}]`)
		end
		return table.concat(parts, " ")
	end,
	GetImageForKeyCode = function()
		local keys = { "ButtonA", "Thumbstick2", "E", "Space" }
		local parts = {}
		for _, key in keys do
			local image: string = input:GetImageForKeyCode(Enum.KeyCode[key])
			table.insert(parts, `{key}=[{string.match(image, "[^/]*$")}]`)
		end
		return table.concat(parts, " ")
	end,
}

return function(target: Frame)
	local names = {}
	for name in reads do
		table.insert(names, name)
	end
	table.sort(names)
	for _, name in names do
		local read = reads[name]
		local ok, value = pcall(read)
		local label = Instance.new("TextLabel")
		label.Name = name
		label.Size = UDim2.fromOffset(400, 20)
		label.Text = if ok then show(value) else `error: {value}`
		label.Parent = target
	end
end
