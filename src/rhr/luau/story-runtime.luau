-- Run one UI story headlessly and save the UI it builds (rhr.story).
--
--   lune run story-runtime.luau <built.rbxl|rbxm> <module path JSON> <out.rbxm> <width> <height> <name> <area JSON> <sizes>
--
-- The built file is the Rojo project; the module path (a JSON list of names from the
-- root) is the story's ModuleScript in it. Every UI library ends in the same calls
-- (Instance.new, set properties, parent), so this copies the Roblox side, not any
-- library: Lune's own instances (properties, datatypes, Enums, saving), plus events,
-- the services UI code touches, require by instance or relative path, and frames on
-- story time that let the UI settle. Story forms: function(target) (Hoarcekat, UI Labs);
-- UI Labs tables with react/reactRoblox, roact, fusion, vide or a generic render;
-- Flipbook's table.
-- The area ({"insets": [left, top, right, bottom], "topbar": height, "input": kind,
-- "displaySize": size}) is where a default ScreenGui sits on that screen, as a
-- game's own UI does in Play, and the device's input and display size. The story's
-- ScreenGui is that size, and GetGuiInset reads the top bar. It is Sibling, as UI
-- Labs mounts stories (Instance.new gives Global). Player settings read Roblox's
-- defaults, as in a Studio play-test.
-- With sizes "on", rhr.story answers layout passes (see Layout passes) over stdin.
-- Scripts' own threads are left behind: the process exits once the UI is saved.
local roblox = require("@lune/roblox")
local fs = require("@lune/fs")
local luau = require("@lune/luau")
local process = require("@lune/process")
local serde = require("@lune/serde")
local stdio = require("@lune/stdio")

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

-- Story time ------------------------------------------------------------------------
-- The story's threads run here, not on Lune's scheduler: Lune runs its queued threads
-- whenever the runtime waits on I/O, as it does for a layout pass, and its clock is
-- the machine's. Story time is the frame count over 60, so a timer fires on the frame
-- it would in a game at 60 fps, however long a frame takes here.
local storyFrame = 0
local function now()
	return storyFrame / 60
end
local deferred, sleeping = {}, {}
local pending = {} -- thread -> the deferred or sleeping entry due to resume it
local sleeps = 0

local function resume(thread, ...)
	pending[thread] = nil
	local okResume, problem = coroutine.resume(thread, ...)
	if not okResume then
		stdio.ewrite(debug.traceback(thread, tostring(problem)) .. "\n")
	end
end
local function threadOf(fn)
	return if type(fn) == "thread" then fn else coroutine.create(fn)
end
local function sleep(seconds, entry)
	sleeps += 1
	entry.due = now() + math.max(tonumber(seconds) or 0, 0)
	entry.order = sleeps
	pending[entry.thread] = entry
	table.insert(sleeping, entry)
end
local function wake(entry)
	if pending[entry.thread] ~= entry then
		return false
	end
	if entry.start then
		resume(entry.thread, now() - entry.start)
	else
		resume(entry.thread, table.unpack(entry.args, 1, entry.args.n))
	end
	return true
end

local storyTask = {}
function storyTask.spawn(fn, ...)
	local thread = threadOf(fn)
	resume(thread, ...)
	return thread
end
function storyTask.defer(fn, ...)
	local thread = threadOf(fn)
	local entry = { thread = thread, args = table.pack(...) }
	pending[thread] = entry
	table.insert(deferred, entry)
	return thread
end
function storyTask.delay(seconds, fn, ...)
	local thread = threadOf(fn)
	sleep(seconds, { thread = thread, args = table.pack(...) })
	return thread
end
function storyTask.wait(seconds)
	sleep(seconds, { thread = coroutine.running(), start = now() })
	return coroutine.yield()
end
function storyTask.cancel(thread)
	pending[thread] = nil
	pcall(coroutine.close, thread)
end

-- Deferred threads run at the end of each step of a frame, as Roblox runs them at its
-- resumption points; those they defer in turn run in the same drain.
local DRAIN_ROUNDS = 100
local drainWarned = false
local function drain()
	local ran = 0
	for _ = 1, DRAIN_ROUNDS do
		if #deferred == 0 then
			return ran
		end
		local batch = deferred
		deferred = {}
		for _, entry in batch do
			if wake(entry) then
				ran += 1
			end
		end
	end
	if not drainWarned then
		drainWarned = true
		stdio.ewrite(`task.defer went on deferring for {DRAIN_ROUNDS} rounds; the rest ran a step later\n`)
	end
	return ran
end

-- Timers due by now, in the order they fall due.
local function wakeSleepers()
	local time, due, rest = now(), {}, {}
	for _, entry in sleeping do
		if pending[entry.thread] == entry then
			table.insert(if entry.due <= time + 1e-9 then due else rest, entry)
		end
	end
	sleeping = rest
	table.sort(due, function(a, b)
		return if a.due ~= b.due then a.due < b.due else a.order < b.order
	end)
	for _, entry in due do
		wake(entry)
	end
end

-- Signals ---------------------------------------------------------------------------
-- Library code checks typeof(x) == "RBXScriptSignal": the sandbox's typeof reads __type.
local Signal = { __type = "RBXScriptSignal" }
Signal.__index = Signal
local Connection = { __type = "RBXScriptConnection" }
Connection.__index = Connection

local connections = 0
function Signal.new()
	return setmetatable({ handlers = {} }, Signal)
end
function Signal:Connect(fn)
	connections += 1
	local connection = setmetatable({ Connected = true, order = connections }, Connection)
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
-- In the order they connected; one a handler disconnects before its turn is skipped.
function Signal:Fire(...)
	local handlers = self.handlers
	local connected = {}
	for connection in handlers do
		table.insert(connected, connection)
	end
	table.sort(connected, function(a, b)
		return a.order < b.order
	end)
	for _, connection in connected do
		local fn = handlers[connection]
		if fn then
			storyTask.spawn(fn, ...)
		end
	end
end
function Signal:Wait()
	local thread = coroutine.running()
	self:Once(function(...)
		if coroutine.status(thread) == "suspended" then
			resume(thread, ...)
		end
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

-- What Roblox works out as it lays GUI out. Lune has no value for these, so a read
-- would raise: they read as Studio's do on a new element until a layout pass writes
-- the sizes (see Layout passes), except that TextFits and an image's IsLoaded are true,
-- so code that waits for them, or shrinks text until it fits, goes on, and a grid's
-- AbsoluteCellSize is zero, where Studio's is the CellSize it starts with, which a
-- story usually changes.
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
	task = storyTask,
	wait = function(seconds)
		return storyTask.wait(seconds), now()
	end,
	delay = storyTask.delay,
	spawn = storyTask.spawn,
	tick = now,
	time = now,
	elapsedTime = now,
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
base.os = table.clone(os)
base.os.clock = now

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

-- Layout passes ---------------------------------------------------------------------
-- Lune lays nothing out, so rhr.story does, with the render's own layout: at a pass
-- the runtime saves the live screen, prints `RHR-PASS <file>` and reads back one JSON
-- line, {path: {s, p, c, t, cs, w}}, of what Roblox would work out for each element.
-- It writes the values that changed and fires their signals, so the story reads the
-- sizes the render draws, from a signal, a deferred thread or a later frame. A read in
-- the same resumption that parented the element comes before any pass and reads zero,
-- where Roblox lays the element out on the spot.
local SIZES = process.args[8] == "on"
local PASS_FILE = outPath .. ".pass.rbxm"
local FIELDS = { { "s", "AbsoluteSize" }, { "p", "AbsolutePosition" }, { "c", "AbsoluteContentSize" },
	{ "t", "TextBounds" }, { "cs", "AbsoluteCanvasSize" }, { "w", "AbsoluteWindowSize" } }
local passes = { count = 0, settles = {}, changed = 0, seconds = 0, unresolved = 0 }

-- Lune keeps a legacy `Font = Enum.Font.X` as an EnumItem it cannot save: as a FontFace.
-- Roblox keeps whichever of the two was set last, which Lune does not record; UI
-- libraries with defaults (Vide's) set a legacy Font before the story's FontFace, so a
-- FontFace other than the default wins.
local DEFAULT_FACE = roblox.Instance.new("TextLabel").FontFace
local function fixFonts(root)
	for _, instance in root:GetDescendants() do
		if instance:IsA("TextLabel") or instance:IsA("TextButton") or instance:IsA("TextBox") then
			local okFont, legacy = pcall(function()
				return instance.Font -- (reading it fails unless a story set it)
			end)
			if okFont and nativeTypeof(legacy) == "EnumItem" and instance.FontFace == DEFAULT_FACE then
				instance.FontFace = roblox.Font.fromEnum(legacy)
			end
		end
	end
end

-- Elements by the paths RHR's model reader gives them (rhr.ir.ensure_paths): the Name,
-- or the ClassName when it is empty, and every sibling sharing one indexed from 1.
-- Clone, which the pass saves through, leaves out what is not Archivable.
local function pathIndex(root)
	local byPath = {}
	local function visit(children, parentPath)
		local counts, seen, kept = {}, {}, {}
		for _, child in children do
			if child.Archivable then
				local name = if child.Name ~= "" then child.Name else child.ClassName
				counts[name] = (counts[name] or 0) + 1
				table.insert(kept, { child, name })
			end
		end
		for _, item in kept do
			local child, segment = item[1], item[2]
			if counts[segment] > 1 then
				seen[segment] = (seen[segment] or 0) + 1
				segment = `{segment}[{seen[segment]}]`
			end
			local here = if parentPath == "" then segment else `{parentPath}/{segment}`
			byPath[here] = child
			visit(child:GetChildren(), here)
		end
	end
	visit({ root }, "")
	return byPath
end

local function read(instance, property)
	return instance[property]
end
local function layoutPass()
	local began = os.clock()
	local copy = screen:Clone()
	fixFonts(copy)
	local okSave, saveProblem = pcall(function()
		fs.writeFile(PASS_FILE, roblox.serializeModel({ copy }))
	end)
	copy:Destroy()
	if not okSave then
		fail("could not save the screen for a layout pass: " .. tostring(saveProblem))
	end
	stdio.write(`RHR-PASS {PASS_FILE}\n`)
	local okReply, reply = pcall(serde.decode, "json", stdio.readLine())
	if not okReply then
		fail("the layout pass got no answer: " .. tostring(reply))
	end
	local byPath = pathIndex(screen)
	local changed = {}
	for path, values in reply do
		local instance = byPath[path]
		if instance == nil then
			passes.unresolved += 1
			continue
		end
		for _, field in FIELDS do
			local pair = values[field[1]]
			if pair then
				local value = roblox.Vector2.new(pair[1], pair[2])
				local okRead, current = pcall(read, instance, field[2])
				if (not okRead or current ~= value) and pcall(write, instance, field[2], value) then
					table.insert(changed, { instance, field[2] })
				end
			end
		end
	end
	for _, change in changed do
		eventOf(change[1], "property:" .. change[2]):Fire()
		eventOf(change[1], "Changed"):Fire(change[2])
	end
	passes.count += 1
	passes.changed += #changed
	passes.seconds += os.clock() - began
	return #changed
end

-- Roblox works sizes out within the frame, so these passes have no Heartbeat between
-- them: they go on while a pass changes a size or the threads it releases run.
local SETTLE_PASSES = 8
local function settle()
	if not SIZES then
		return
	end
	for count = 1, SETTLE_PASSES do
		local changed = layoutPass()
		if drain() == 0 and changed == 0 then
			table.insert(passes.settles, count)
			return
		end
	end
	table.insert(passes.settles, SETTLE_PASSES)
	stdio.ewrite(`sizes still changed after {SETTLE_PASSES} layout passes in a row: the story may resize what it measures\n`)
end

local runService = game:GetService("RunService")
local function frame()
	storyFrame += 1
	local step = 1 / 60
	for _, fn in renderSteps do
		storyTask.spawn(fn, step)
	end
	runService.RenderStepped:Fire(step)
	runService.PreRender:Fire(step)
	drain()
	if SIZES then
		layoutPass()
		drain()
	end
	wakeSleepers()
	drain()
	runService.Heartbeat:Fire(step)
	drain()
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

-- A story that waits while it mounts gets up to MOUNT_FRAMES frames of story time.
local MOUNT_FRAMES = 300
local mounted, mountProblem = false, nil
storyTask.spawn(function()
	local okMount, problem = xpcall(mount, function(err)
		return tostring(err) .. "\n" .. debug.traceback("", 2)
	end)
	mounted, mountProblem = true, if okMount then nil else problem
end)
if mountProblem then
	fail(mountProblem)
end
settle()
drain()
for _ = 1, MOUNT_FRAMES do
	if mounted then
		break
	end
	frame()
end
if mountProblem then
	fail(mountProblem)
end
if not mounted then
	stdio.ewrite(`the story was still mounting after {MOUNT_FRAMES / 60} s of story time; saved what it had built\n`)
end
for _ = 1, 30 do
	frame()
end
settle()

fixFonts(screen)
local okSave, saveProblem = pcall(function()
	fs.writeFile(outPath, roblox.serializeModel({ screen }))
end)
if not okSave then
	fail("could not save the UI the story built: " .. tostring(saveProblem))
end
if SIZES then
	fs.removeFile(PASS_FILE)
	if passes.unresolved > 0 then
		stdio.ewrite(`{passes.unresolved} layout values named no element of the story's screen\n`)
	end
	print("RHR-SIZES " .. serde.encode("json", passes))
end
print(`ok {#screen:GetDescendants()}`)
process.exit(0)
