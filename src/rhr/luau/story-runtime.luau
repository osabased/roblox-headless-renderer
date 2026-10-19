-- Run one UI story headlessly and save the UI it builds (rhr.story).
--
--   lune run story-runtime.luau <built.rbxl|rbxm> <module path JSON> <out.rbxm> <width> <height> <name> <area JSON>
--
-- The built file is the Rojo project; the module path (a JSON list of names from the
-- root) is the story's ModuleScript in it. Every UI library ends in the same calls
-- (Instance.new, set properties, parent), so this copies the Roblox side, not any
-- library: Lune's own instances (properties, datatypes, Enums, saving), plus events,
-- the services UI code touches, require by instance or relative path, and a frame
-- loop that lets the UI settle. Story forms: function(target) (Hoarcekat, UI Labs);
-- UI Labs tables with react/reactRoblox, roact, fusion, vide or a generic render;
-- Flipbook's table.
-- The area ({"insets": [left, top, right, bottom], "topbar": height, "input": kind,
-- "displaySize": size}) is where a default ScreenGui sits on that screen, as a
-- game's own UI does in Play, and the device's input and display size. The story's
-- ScreenGui is that size, and GetGuiInset reads the top bar. It is Sibling, as UI
-- Labs mounts stories (Instance.new gives Global). Player settings read Roblox's
-- defaults, as in a Studio play-test.
-- Scripts' own threads are left behind: the process exits once the UI is saved.
local roblox = require("@lune/roblox")
local fs = require("@lune/fs")
local luau = require("@lune/luau")
local process = require("@lune/process")
local serde = require("@lune/serde")
local stdio = require("@lune/stdio")
local task = require("@lune/task")

local builtPath, modulePathJson, outPath = process.args[1], process.args[2], process.args[3]
local viewport = roblox.Vector2.new(tonumber(process.args[4]) or 1615, tonumber(process.args[5]) or 1080)
local storyName = process.args[6] or "Story"
local area = serde.decode("json", process.args[7] or '{"insets": [0, 0, 0, 0], "topbar": 0}')
local preferredInput = area.input or "KeyboardAndMouse"
local areaSize = roblox.Vector2.new(
	viewport.X - area.insets[1] - area.insets[3],
	viewport.Y - area.insets[2] - area.insets[4]
)

local function fail(message)
	stdio.ewrite(tostring(message) .. "\n")
	process.exit(1)
end

-- Signals ---------------------------------------------------------------------------
-- Library code checks typeof(x) == "RBXScriptSignal": the sandbox's typeof reads __type.
local Signal = { __type = "RBXScriptSignal" }
Signal.__index = Signal
local Connection = { __type = "RBXScriptConnection" }
Connection.__index = Connection

function Signal.new()
	return setmetatable({ handlers = {} }, Signal)
end
function Signal:Connect(fn)
	local connection = setmetatable({ Connected = true }, Connection)
	local handlers = self.handlers
	handlers[connection] = fn
	function connection.Disconnect()
		connection.Connected = false
		handlers[connection] = nil
	end
	connection.disconnect = connection.Disconnect
	return connection
end
Signal.connect = Signal.Connect
function Signal:Once(fn)
	local connection
	connection = self:Connect(function(...)
		connection.Disconnect()
		fn(...)
	end)
	return connection
end
function Signal:Fire(...)
	for _, fn in self.handlers do
		task.spawn(fn, ...)
	end
end
function Signal:Wait()
	local thread = coroutine.running()
	self:Once(function(...)
		task.spawn(thread, ...)
	end)
	return coroutine.yield()
end

local signals = setmetatable({}, { __mode = "k" })
local function eventOf(instance, key)
	local byKey = signals[instance]
	if not byKey then
		byKey = {}
		signals[instance] = byKey
	end
	local signal = byKey[key]
	if not signal then
		signal = Signal.new()
		byKey[key] = signal
	end
	return signal
end

local EVENTS = {
	Instance = { "Changed", "ChildAdded", "ChildRemoved", "DescendantAdded", "DescendantRemoving",
		"AncestryChanged", "Destroying", "AttributeChanged" },
	GuiObject = { "InputBegan", "InputEnded", "InputChanged", "MouseEnter", "MouseLeave", "MouseMoved",
		"MouseWheelForward", "MouseWheelBackward", "TouchTap", "TouchLongPress", "TouchPan", "TouchPinch",
		"TouchRotate", "TouchSwipe", "SelectionGained", "SelectionLost", "SelectionChanged" },
	GuiButton = { "Activated", "MouseButton1Click", "MouseButton1Down", "MouseButton1Up", "MouseButton2Click",
		"MouseButton2Down", "MouseButton2Up" },
	TextBox = { "FocusLost", "Focused", "ReturnPressedFromOnScreenKeyboard" },
	RunService = { "Heartbeat", "RenderStepped", "Stepped", "PreRender", "PreAnimation", "PreSimulation",
		"PostSimulation" },
	UserInputService = { "InputBegan", "InputEnded", "InputChanged", "LastInputTypeChanged", "TouchStarted",
		"TouchEnded", "TouchMoved", "WindowFocused", "WindowFocusReleased", "JumpRequest", "GamepadConnected",
		"GamepadDisconnected" },
	Players = { "PlayerAdded", "PlayerRemoving" },
	Player = { "CharacterAdded", "CharacterRemoving", "Chatted" },
	GuiService = { "MenuOpened", "MenuClosed" },
	BindableEvent = { "Event" },
	RemoteEvent = { "OnClientEvent", "OnServerEvent" },
}
for className, names in EVENTS do
	for _, name in names do
		pcall(roblox.implementProperty, className, name, function(instance)
			return eventOf(instance, name)
		end)
	end
end
roblox.implementMethod("Instance", "GetPropertyChangedSignal", function(instance, property)
	return eventOf(instance, "property:" .. property)
end)
roblox.implementMethod("Instance", "GetAttributeChangedSignal", function(instance, attribute)
	return eventOf(instance, "attribute:" .. attribute)
end)
roblox.implementMethod("Instance", "WaitForChild", function(instance, name)
	return instance:FindFirstChild(name)
end)
roblox.implementMethod("BindableEvent", "Fire", function(instance, ...)
	eventOf(instance, "Event"):Fire(...)
end)
roblox.implementMethod("RemoteEvent", "FireServer", function() end)
roblox.implementMethod("RemoteFunction", "InvokeServer", function()
	return nil
end)
for name, value in { IsClient = true, IsServer = false, IsStudio = true, IsRunning = true, IsEdit = false,
	IsRunMode = false } do
	roblox.implementMethod("RunService", name, function()
		return value
	end)
end
local renderSteps = {}
roblox.implementMethod("RunService", "BindToRenderStep", function(_, name, _priority, fn)
	renderSteps[name] = fn
end)
roblox.implementMethod("RunService", "UnbindFromRenderStep", function(_, name)
	renderSteps[name] = nil
end)
local LAST_INPUT = { KeyboardAndMouse = "MouseButton1", Touch = "Touch", Gamepad = "Gamepad1" }
roblox.implementMethod("UserInputService", "GetLastInputType", function()
	return roblox.Enum.UserInputType[LAST_INPUT[preferredInput]]
end)
roblox.implementMethod("UserInputService", "GetMouseLocation", function()
	return roblox.Vector2.new(0, 0)
end)
roblox.implementMethod("GuiService", "GetGuiInset", function()
	return roblox.Vector2.new(0, area.topbar), roblox.Vector2.new(0, 0)
end)
roblox.implementMethod("GuiService", "IsTenFootInterface", function()
	return preferredInput == "Gamepad"
end)
roblox.implementMethod("GuiService", "GetEmotesMenuOpen", function()
	return false
end)
roblox.implementMethod("GuiService", "GetInspectMenuEnabled", function()
	return true
end)

-- The console preset has a gamepad connected, which the other presets lack.
local function connectedGamepads()
	return if preferredInput == "Gamepad" then { roblox.Enum.UserInputType.Gamepad1 } else {}
end
local function gamepadIsConnected(gamepad)
	return table.find(connectedGamepads(), gamepad) ~= nil
end
roblox.implementMethod("UserInputService", "GetConnectedGamepads", connectedGamepads)
roblox.implementMethod("UserInputService", "GetGamepadConnected", function(_, gamepad)
	return gamepadIsConnected(gamepad)
end)
-- Studio counts all eight gamepads as navigation gamepads, connected or not, until
-- SetNavigationGamepad turns one off; it ignores the call for other input types.
local navigates = {}
for slot = 1, 8 do
	navigates[`Gamepad{slot}`] = true
end
roblox.implementMethod("UserInputService", "GetNavigationGamepads", function()
	local gamepads = {}
	for slot = 1, 8 do
		if navigates[`Gamepad{slot}`] then
			table.insert(gamepads, roblox.Enum.UserInputType[`Gamepad{slot}`])
		end
	end
	return gamepads
end)
roblox.implementMethod("UserInputService", "IsNavigationGamepad", function(_, gamepad)
	return navigates[gamepad.Name] == true
end)
roblox.implementMethod("UserInputService", "SetNavigationGamepad", function(_, gamepad, enabled)
	if navigates[gamepad.Name] ~= nil then
		navigates[gamepad.Name] = enabled == true
	end
end)
local GAMEPAD_KEYS =
	{ "ButtonX", "ButtonY", "ButtonA", "ButtonB", "ButtonR1", "ButtonL1", "ButtonR2", "ButtonL2", "ButtonR3",
		"ButtonL3", "ButtonStart", "ButtonSelect", "DPadLeft", "DPadRight", "DPadUp", "DPadDown", "Thumbstick1",
		"Thumbstick2" }
roblox.implementMethod("UserInputService", "GetSupportedGamepadKeyCodes", function(_, gamepad)
	local keys = {}
	if gamepadIsConnected(gamepad) then
		for _, name in GAMEPAD_KEYS do
			table.insert(keys, roblox.Enum.KeyCode[name])
		end
	end
	return keys
end)
-- Nothing is held down and no pointer has moved while a story runs.
for name, value in { IsKeyDown = false, IsMouseButtonPressed = false, IsGamepadButtonDown = false } do
	roblox.implementMethod("UserInputService", name, function()
		return value
	end)
end
for _, name in { "GetKeysPressed", "GetMouseButtonsPressed" } do
	roblox.implementMethod("UserInputService", name, function()
		return {}
	end)
end
roblox.implementMethod("UserInputService", "GetMouseDelta", function()
	return roblox.Vector2.new(0, 0)
end)
roblox.implementMethod("UserInputService", "GetFocusedTextBox", function()
	return nil
end)
roblox.implementMethod("UserInputService", "GetUserCFrame", function()
	return roblox.CFrame.identity
end)

-- What GetStringForKeyCode gives on a US keyboard: the key's letter, or the character on
-- the key without Shift. Keys with no printable character, and the Mouse and Touch
-- codes, give "".
local KEY_STRINGS = {
	Space = " ", QuotedDouble = "'", Hash = "3", Dollar = "4", Percent = "5", Ampersand = "7", Quote = "'",
	LeftParenthesis = "9", RightParenthesis = "0", Asterisk = "8", Plus = "=", Comma = ",", Minus = "-",
	Period = ".", Slash = "/", Zero = "0", One = "1", Two = "2", Three = "3", Four = "4", Five = "5", Six = "6",
	Seven = "7", Eight = "8", Nine = "9", Colon = ";", Semicolon = ";", LessThan = ",", Equals = "=",
	GreaterThan = ".", Question = "/", At = "2", LeftBracket = "[", BackSlash = "\\", RightBracket = "]",
	Caret = "6", Underscore = "-", Backquote = "`", LeftCurly = "[", Pipe = "\\", RightCurly = "]", Tilde = "`",
	KeypadMinus = "-", KeypadPlus = "+", Print = "*",
}
local IMAGE_BASE = "rbxasset://textures/ui/Controls/DefaultController/"
roblox.implementMethod("UserInputService", "GetStringForKeyCode", function(_, key)
	local name = key.Name
	if string.match(name, "^%u$") or table.find(GAMEPAD_KEYS, name) then
		return name
	end
	return KEY_STRINGS[name] or ""
end)
roblox.implementMethod("UserInputService", "GetImageForKeyCode", function(_, key)
	local name = key.Name
	if table.find(GAMEPAD_KEYS, name) then
		return `{IMAGE_BASE}{name}@2x.png`
	end
	return ""
end)
local function shownWithin(object, root)
	while object ~= root do
		if object:IsA("GuiObject") and not object.Visible then
			return false
		end
		object = object.Parent
	end
	return true
end
roblox.implementMethod("GuiService", "Select", function(service, parent)
	local chosen
	for _, object in parent:GetDescendants() do
		if object:IsA("GuiObject") and object.Selectable and shownWithin(object, parent)
			and (chosen == nil or object.SelectionOrder < chosen.SelectionOrder) then
			chosen = object
		end
	end
	if chosen then
		service.SelectedObject = chosen
	end
end)
roblox.implementMethod("Players", "GetPlayers", function(players)
	return players:GetChildren()
end)

-- Tweens finish at once: a still picture shows where they end.
local TweenInfo = roblox.TweenInfo
	or {
		new = function(time, style, direction, repeats, reverses, delay)
			return { Time = time or 1, EasingStyle = style, EasingDirection = direction, RepeatCount = repeats or 0,
				Reverses = reverses or false, DelayTime = delay or 0 }
		end,
	}
roblox.implementMethod("TweenService", "Create", function(_, instance, _info, goals)
	local tween = { Completed = Signal.new(), PlaybackState = roblox.Enum.PlaybackState.Begin }
	function tween.Play()
		for property, value in goals do
			instance[property] = value
		end
		tween.PlaybackState = roblox.Enum.PlaybackState.Completed
		tween.Completed:Fire(roblox.Enum.PlaybackState.Completed)
	end
	return setmetatable(tween, {
		__index = function()
			return function() end
		end,
	})
end)
roblox.implementMethod("TweenService", "GetValue", function(_, alpha)
	return alpha
end)
-- Text measures: a rough width (RHR's own text engine lays the text out afterwards).
roblox.implementMethod("TextService", "GetTextSize", function(_, text, size)
	return roblox.Vector2.new(#tostring(text) * size * 0.5, size)
end)
roblox.implementMethod("TextService", "GetTextBoundsAsync", function(_, params)
	local size, wrap = params.Size, params.Width
	local widest, lines = 0, 0
	for _, line in string.split(params.Text, "\n") do
		local width = #line * size * 0.5
		if wrap > 0 and width > wrap then
			widest = wrap
			lines += math.ceil(width / wrap)
		else
			widest = math.max(widest, width)
			lines += 1
		end
	end
	return roblox.Vector2.new(widest, lines * size)
end)
local guids = 0
roblox.implementMethod("HttpService", "GenerateGUID", function(_, braces)
	guids += 1
	local id = string.format("%08X-0000-4000-8000-%012X", guids, guids)
	return if braces == false then id else "{" .. id .. "}"
end)
roblox.implementMethod("HttpService", "JSONEncode", function(_, value)
	return serde.encode("json", value)
end)
roblox.implementMethod("HttpService", "JSONDecode", function(_, text)
	return serde.decode("json", text)
end)

-- What Roblox works out as it lays GUI out, which RHR does only after the story ran.
-- Lune has no value for these, so a read would raise: they read as Studio's do on a new
-- element, except that TextFits and an image's IsLoaded are true, so code that waits
-- for them, or shrinks text until it fits, goes on, and a grid's AbsoluteCellSize is
-- zero, where Studio's is the CellSize it starts with, which a story usually changes.
local ZERO = roblox.Vector2.new(0, 0)
local TEXT = { TextBounds = ZERO, TextFits = true, OpenTypeFeaturesError = "" }
local IMAGE = { IsLoaded = true }
local COMPUTED = {
	{ "GuiBase2d", { AbsoluteSize = ZERO, AbsolutePosition = ZERO, AbsoluteRotation = 0 } },
	{ "GuiObject", { GuiState = roblox.Enum.GuiState.Idle } },
	{ "TextLabel", TEXT },
	{ "TextButton", TEXT },
	{ "TextBox", TEXT },
	{ "TextBox", { CursorPosition = 1, SelectionStart = -1 } },
	{ "ImageLabel", IMAGE },
	{ "ImageButton", IMAGE },
	{ "VideoFrame", { IsLoaded = false, Resolution = ZERO, TimeLength = 0 } },
	{ "ScrollingFrame", { AbsoluteCanvasSize = ZERO, AbsoluteWindowSize = ZERO } },
	{ "BillboardGui", { CurrentDistance = 0, DistanceStep = 0 } },
	{ "UIGridStyleLayout", { AbsoluteContentSize = ZERO } },
	{ "UIGridLayout", { AbsoluteCellCount = ZERO, AbsoluteCellSize = ZERO } },
}
local function write(instance, property, value)
	instance[property] = value
end
local function presetComputed(instance)
	for _, preset in COMPUTED do
		if instance:IsA(preset[1]) then
			for property, value in preset[2] do
				pcall(write, instance, property, value)
			end
		end
	end
end

-- The data model ------------------------------------------------------------------------
local ok, game = pcall(function()
	local data = fs.readFile(builtPath)
	if string.sub(builtPath, -5) == ".rbxl" or string.sub(builtPath, -6) == ".rbxlx" then
		return roblox.deserializePlace(data)
	end
	local model = roblox.Instance.new("DataModel")
	local holder = model:GetService("ReplicatedStorage")
	for _, root in roblox.deserializeModel(data) do
		root.Parent = holder
	end
	return model
end)
if not ok then
	fail("could not read the built project: " .. tostring(game))
end
for _, instance in game:GetDescendants() do
	presetComputed(instance)
end
local workspace = game:GetService("Workspace")
local camera = workspace.CurrentCamera or roblox.Instance.new("Camera")
camera.Parent = workspace
workspace.CurrentCamera = camera
pcall(function()
	camera.ViewportSize = viewport
end)
local userInput = game:GetService("UserInputService")
userInput.PreferredInput = roblox.Enum.PreferredInput[preferredInput]
userInput.TouchEnabled = preferredInput == "Touch"
userInput.KeyboardEnabled = preferredInput == "KeyboardAndMouse"
userInput.MouseEnabled = preferredInput == "KeyboardAndMouse"
userInput.GamepadEnabled = preferredInput == "Gamepad"
local guiService = game:GetService("GuiService")
guiService.ViewportDisplaySize = roblox.Enum.DisplaySize[area.displaySize or "Medium"]
guiService.PreferredTextSize = roblox.Enum.PreferredTextSize.Medium
guiService.PreferredTransparency = 1
guiService.ReducedMotionEnabled = false
-- RHR draws none of Roblox's top-bar buttons, so the whole bar between the device's
-- side insets is free.
guiService.TopbarInset = roblox.Rect.new(area.insets[1], 0, viewport.X - area.insets[3], area.topbar)

-- Lune's reflection data has no default for these, so reading one that was never set is an
-- error. They start at what a Studio play-test reads.
guiService.AutoSelectGuiEnabled = true
guiService.CoreGuiNavigationEnabled = true
guiService.GuiNavigationEnabled = true
guiService.IsModalDialog = false
guiService.IsWindows = true
guiService.MenuIsOpen = false
guiService.TouchControlsEnabled = true
userInput.AccelerometerEnabled = false
userInput.GyroscopeEnabled = false
userInput.ModalEnabled = false
userInput.VREnabled = false
userInput.MouseBehavior = roblox.Enum.MouseBehavior.Default
userInput.MouseDeltaSensitivity = 1
userInput.MouseIcon = ""
userInput.MouseIconContent = roblox.Content.none
userInput.MouseIconEnabled = true
userInput.OnScreenKeyboardPosition = roblox.Vector2.new(0, 0)
userInput.OnScreenKeyboardSize = roblox.Vector2.new(0, 0)
userInput.OnScreenKeyboardVisible = false
userInput.UserHeadCFrame = roblox.CFrame.identity
local players = game:GetService("Players")
local localPlayer = players:FindFirstChildOfClass("Player") or roblox.Instance.new("Player")
localPlayer.Name = if localPlayer.Name == "Player" or localPlayer.Name == "" then "Player" else localPlayer.Name
localPlayer.Parent = players
pcall(roblox.implementProperty, "Players", "LocalPlayer", function()
	return localPlayer
end)
pcall(function()
	players.LocalPlayer = localPlayer
end)
local playerGui = localPlayer:FindFirstChildOfClass("PlayerGui") or roblox.Instance.new("PlayerGui")
playerGui.Parent = localPlayer

-- Modules -------------------------------------------------------------------------------
local loaded, loading = {}, {}
local base

-- Roblox's require-by-string (pesde's package links use it): ./x is a sibling of the
-- requiring script, ../x a sibling of its parent, @self/x its child.
local function resolvePath(path, from)
	local node, rest
	if string.sub(path, 1, 6) == "@self/" then
		node, rest = from, string.sub(path, 7)
	elseif string.sub(path, 1, 2) == "./" or string.sub(path, 1, 3) == "../" then
		node, rest = from.Parent, path
	else
		error(`require("{path}") is not supported when running a story (only paths that start with ./, ../ or @self/)`, 4)
	end
	for segment in string.gmatch(rest, "[^/]+") do
		local nextNode = node
		if segment == ".." then
			nextNode = node.Parent
		elseif segment ~= "." then
			nextNode = node:FindFirstChild(segment)
		end
		if nextNode == nil then
			local missing = if segment == ".." then "no parent" else `no child named {segment}`
			error(`require("{path}"): {node:GetFullName()} has {missing}`, 4)
		end
		node = nextNode
	end
	return node
end

local function requireModule(target, from)
	if type(target) == "string" then
		target = resolvePath(target, from)
	end
	if typeof(target) ~= "Instance" then
		error(`require({typeof(target)}) is not supported when running a story (only ModuleScripts in the project)`, 3)
	end
	if not target:IsA("ModuleScript") then
		error(`{target:GetFullName()} is not a ModuleScript`, 3)
	end
	if loaded[target] ~= nil then
		return loaded[target]
	end
	if loading[target] then
		error(`require loop at {target:GetFullName()}`, 3)
	end
	loading[target] = true
	local environment = table.clone(base) -- (copied: Lune's load() sets its own metatable)
	environment.script = target
	environment.require = function(module)
		return requireModule(module, target)
	end
	local chunk = luau.load(target.Source, { debugName = target:GetFullName(), environment = environment })
	local result = chunk()
	loading[target] = nil
	loaded[target] = if result == nil then true else result
	return result
end

local nativeTypeof = typeof
base = {
	game = game,
	Game = game,
	workspace = workspace,
	Workspace = workspace,
	shared = {},
	Instance = {
		new = function(className, parent)
			local instance = roblox.Instance.new(className)
			presetComputed(instance)
			if instance:IsA("GuiButton") or instance:IsA("TextBox") then
				instance.InputSink = roblox.Enum.InputSink.Activate
			end
			if parent then
				instance.Parent = parent
			end
			return instance
		end,
	},
	Enum = roblox.Enum,
	TweenInfo = TweenInfo,
	task = task,
	wait = task.wait,
	delay = task.delay,
	spawn = task.spawn,
	tick = os.clock,
	time = os.clock,
	elapsedTime = os.clock,
	settings = function()
		return {}
	end,
	UserSettings = function()
		return { GetService = function() return {} end }
	end,
	warn = function(...)
		stdio.ewrite("[warn] " .. table.concat(table.pack(...) :: any, " ") .. "\n")
	end,
	print = function() end, -- a story's prints are noise in a render
	-- The way from a story's globals to Lune's own (getfenv(0).require reaches
	-- @lune/process). Not a sandbox: a story still runs with Lune's powers in reach;
	-- the docs say not to run untrusted ones.
	getfenv = function()
		error("getfenv is not available when running a story", 2)
	end,
	setfenv = function()
		error("setfenv is not available when running a story", 2)
	end,
	typeof = function(value)
		if type(value) == "table" then
			local meta = getmetatable(value)
			if type(meta) == "table" and type(rawget(meta, "__type")) == "string" then
				return meta.__type
			end
		end
		return nativeTypeof(value)
	end,
}
for _, name in { "UDim", "UDim2", "Vector2", "Vector3", "Vector2int16", "Vector3int16", "Color3", "ColorSequence",
	"ColorSequenceKeypoint", "NumberSequence", "NumberSequenceKeypoint", "NumberRange", "Rect", "CFrame",
	"BrickColor", "Font", "Faces", "Axes", "Ray", "Region3", "PhysicalProperties", "Random", "DateTime",
	"Content", "OverlapParams", "RaycastParams" } do
	if roblox[name] ~= nil then
		base[name] = roblox[name]
	end
end
-- Roblox's profiler and memory categories, which UI libraries call every frame
-- (Vide's scheduler); Lune's debug library has neither.
base.debug = table.clone(debug)
for _, name in { "profilebegin", "profileend", "setmemorycategory", "resetmemorycategory" } do
	base.debug[name] = function() end
end

-- Run -----------------------------------------------------------------------------------
local storyScript = game
for _, name in serde.decode("json", modulePathJson) do
	local child = storyScript:FindFirstChild(name)
	if not child then
		fail(`the story's module {name} was not found under {storyScript:GetFullName()} in the built project`)
	end
	storyScript = child
end

local screen = roblox.Instance.new("ScreenGui")
screen.Name = storyName
screen.ZIndexBehavior = roblox.Enum.ZIndexBehavior.Sibling
screen.ResetOnSpawn = false
screen.Parent = playerGui
local target = roblox.Instance.new("Frame")
target.Name = "Target"
target.Size = roblox.UDim2.fromScale(1, 1)
target.BackgroundTransparency = 1
target.Parent = screen
presetComputed(screen)
presetComputed(target)
-- Roblox measures AbsolutePosition from the area's corner, so theirs stays 0,0.
pcall(function()
	screen.AbsoluteSize = areaSize
	target.AbsoluteSize = areaSize
end)

local runService = game:GetService("RunService")
local function frames(count)
	for _ = 1, count do
		for _, fn in renderSteps do
			task.spawn(fn, 1 / 60)
		end
		runService.RenderStepped:Fire(1 / 60)
		runService.PreRender:Fire(1 / 60)
		runService.Heartbeat:Fire(1 / 60)
		task.wait()
	end
end

local function controlDefaults(controls)
	local values = {}
	for name, control in controls or {} do
		if type(control) == "table" then
			local value = control.ControlValue
			if value == nil then value = control.Default end
			if value == nil then value = control.default end
			if value == nil then value = control.__default end
			if value == nil and type(control.List) == "table" then value = control.List[1] end
			values[name] = value
		else
			values[name] = control
		end
	end
	return values
end

local function mount()
	local story = requireModule(storyScript)
	if type(story) == "function" then
		return story(target)
	end
	if type(story) ~= "table" then
		error("a story module returns a function(target) or a story table; this one returned a " .. typeof(story))
	end
	local controls = controlDefaults(story.controls)
	local props = { target = target, controls = controls, converted = {}, subscribe = function()
		return function() end
	end }
	if story.react and story.reactRoblox then
		local React, ReactRoblox = story.react, story.reactRoblox
		local element = story.story
		if type(element) == "function" then
			element = React.createElement(element, props)
		end
		local root = if story.renderer == "legacy" and ReactRoblox.createLegacyRoot
			then ReactRoblox.createLegacyRoot(target)
			else ReactRoblox.createRoot(target)
		root:render(element)
		return
	end
	if story.roact then
		local Roact = story.roact
		local element = story.story
		if type(element) == "function" then
			element = Roact.createElement(element, props)
		end
		Roact.mount(element, target)
		return
	end
	if story.vide then
		story.vide.mount(function()
			return story.story(props)
		end, target)
		return
	end
	if type(story.render) == "function" then
		return story.render(props)
	end
	if story.fusion and type(story.story) == "function" then
		props.scope = story.fusion.scoped and story.fusion.scoped(story.fusion)
		return story.story(props)
	end
	if type(story.story) == "function" then
		return story.story(target, props)
	end
	error("a story table needs react + reactRoblox, roact, vide, fusion, a render function or a story function")
end

local okMount, problem = xpcall(mount, function(err)
	return tostring(err) .. "\n" .. debug.traceback("", 2)
end)
if not okMount then
	fail(problem)
end
frames(30)

-- Lune keeps a legacy `Font = Enum.Font.X` as an EnumItem it cannot save: as a FontFace.
-- Roblox keeps whichever of the two was set last, which Lune does not record; UI
-- libraries with defaults (Vide's) set a legacy Font before the story's FontFace, so a
-- FontFace other than the default wins.
local DEFAULT_FACE = roblox.Instance.new("TextLabel").FontFace
for _, instance in screen:GetDescendants() do
	if instance:IsA("TextLabel") or instance:IsA("TextButton") or instance:IsA("TextBox") then
		local okFont, legacy = pcall(function()
			return instance.Font -- (reading it fails unless a story set it)
		end)
		if okFont and nativeTypeof(legacy) == "EnumItem" and instance.FontFace == DEFAULT_FACE then
			instance.FontFace = roblox.Font.fromEnum(legacy)
		end
	end
end
local okSave, saveProblem = pcall(function()
	fs.writeFile(outPath, roblox.serializeModel({ screen }))
end)
if not okSave then
	fail("could not save the UI the story built: " .. tostring(saveProblem))
end
print(`ok {#screen:GetDescendants()}`)
process.exit(0)
