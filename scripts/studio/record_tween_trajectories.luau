-- Tweens as Roblox plays them, for tests/fixtures/tween/trajectories.json.
--
-- Run it in Studio Play mode on the client (the Studio MCP's execute_luau with the
-- Client datamodel) with Studio's viewport on screen: a client steps its tweens only
-- while it renders. It plays a set of tweens on frames in a temporary ScreenGui,
-- samples every Heartbeat for RECORD_S seconds and removes the ScreenGui. The JSON
-- is longer than execute_luau returns in one call, so it is left in StringValues
-- under PlayerGui.RHRTweenRecordingOut, CHUNK characters each, and the script
-- returns how many there are; read them in order, then stop Play mode.
--
-- Time is read from a clock probe: a Linear tween of a NumberValue from 0 to 100
-- over 100 s, played in the same block as the tweens under test, so its value is
-- the engine's own elapsed time for them, whatever phase of the frame a sample is
-- taken in, to within 3 us: Studio rounds a tween's progress to about 2^-25 of its
-- length. A tween played later (an action) gets a probe of its own, played with
-- it. os.clock() is recorded beside each sample for the spread.

local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")

local RECORD_S = 4.5
local CHUNK = 60000

local gui = Instance.new("ScreenGui")
gui.Name = "RHRTweenRecording"
gui.Parent = Players.LocalPlayer:WaitForChild("PlayerGui")

local function encode(value)
	local kind = typeof(value)
	if kind == "UDim2" then
		return { value.X.Scale, value.X.Offset, value.Y.Scale, value.Y.Offset }
	elseif kind == "UDim" then
		return { value.Scale, value.Offset }
	elseif kind == "Color3" then
		return { value.R, value.G, value.B }
	elseif kind == "Vector2" then
		return { value.X, value.Y }
	elseif kind == "EnumItem" then
		return value.Name
	end
	return value
end

local function frame(name, props)
	local instance = Instance.new("Frame")
	instance.Name = name
	for key, value in props do
		instance[key] = value
	end
	instance.Parent = gui
	return instance
end

local function probe()
	local value = Instance.new("NumberValue")
	value.Parent = gui
	local tween = TweenService:Create(value, TweenInfo.new(100, Enum.EasingStyle.Linear), { Value = 100 })
	return value, tween
end

local tracks = {}
local function track(name, instance, property)
	tracks[#tracks + 1] = { name = name, instance = instance, property = property }
end

local tweens, tweenNames = {}, {}
local completions, events, actions = {}, {}, {}
local mainProbe, mainProbeTween = probe()
local clock0 = os.clock()

local function now()
	return mainProbe.Value, os.clock() - clock0
end

local function create(name, instance, info, goals)
	local tween = TweenService:Create(instance, info, goals)
	tweens[name] = tween
	tweenNames[#tweenNames + 1] = name
	tween.Completed:Connect(function(state)
		local e, clock = now()
		local at = {}
		for property in goals do
			at[property] = encode(instance[property])
		end
		completions[#completions + 1] = { tween = name, state = state.Name, e = e, clock = clock, values = at }
	end)
	return tween
end

local function callback(name)
	return function(status)
		local e, clock = now()
		events[#events + 1] = { callback = name, status = status.Name, e = e, clock = clock }
	end
end

local Style, Direction = Enum.EasingStyle, Enum.EasingDirection

-- Every tween below is played in one block, with the main probe.
local A = frame("A", { Position = UDim2.new() })
create("A", A, TweenInfo.new(1, Style.Quad, Direction.Out), { Position = UDim2.new(0.5, 300, 0.25, 100) })
track("A.Position", A, "Position")

local A2 = frame("A2", { Visible = true, BackgroundTransparency = 0 })
create("A2", A2, TweenInfo.new(1, Style.Linear), { Visible = false, BackgroundTransparency = 1 })
track("A2.Visible", A2, "Visible")
track("A2.BackgroundTransparency", A2, "BackgroundTransparency")

local B = frame("B", { Position = UDim2.new() })
create("B", B, TweenInfo.new(0.4, Style.Sine, Direction.InOut, 2, true, 0.2), { Position = UDim2.fromOffset(200, 0) })
track("B.Position", B, "Position")

local B2 = frame("B2", { Rotation = 0 })
create("B2", B2, TweenInfo.new(0.5, Style.Quad, Direction.In, 1, false, 0.3), { Rotation = 45 })
track("B2.Rotation", B2, "Rotation")

local C = frame("C", { Rotation = 0 })
create("C", C, TweenInfo.new(0.6, Style.Linear, Direction.In, -1, false), { Rotation = 90 })
track("C.Rotation", C, "Rotation")

local C2 = frame("C2", { BackgroundTransparency = 0 })
create("C2", C2, TweenInfo.new(0.5, Style.Quad, Direction.Out, -1, true), { BackgroundTransparency = 1 })
track("C2.BackgroundTransparency", C2, "BackgroundTransparency")

local D = frame("D", { BackgroundTransparency = 0 })
create("D", D, TweenInfo.new(1, Style.Linear), { BackgroundTransparency = 1 })
track("D.BackgroundTransparency", D, "BackgroundTransparency")

local E = frame("E", { Size = UDim2.fromOffset(100, 100) })
create("E", E, TweenInfo.new(1, Style.Cubic, Direction.In), { Size = UDim2.fromOffset(200, 50) })
track("E.Size", E, "Size")

local F = frame("F", { Position = UDim2.new(), BackgroundTransparency = 0 })
create("F1", F, TweenInfo.new(1, Style.Linear), { Position = UDim2.fromOffset(0, 100), BackgroundTransparency = 1 })
track("F.Position", F, "Position")
track("F.BackgroundTransparency", F, "BackgroundTransparency")

local G = frame("G", { BackgroundColor3 = Color3.new(1, 0, 0) })
create("G", G, TweenInfo.new(1, Style.Linear), { BackgroundColor3 = Color3.new(0, 0, 1) })
track("G.BackgroundColor3", G, "BackgroundColor3")

local G2 = frame("G2", { AnchorPoint = Vector2.new(0, 0) })
create("G2", G2, TweenInfo.new(1, Style.Back, Direction.Out), { AnchorPoint = Vector2.new(1, 1) })
track("G2.AnchorPoint", G2, "AnchorPoint")

local G3 = frame("G3", {})
local corner = Instance.new("UICorner")
corner.CornerRadius = UDim.new(0, 0)
corner.Parent = G3
create("G3", corner, TweenInfo.new(1, Style.Bounce, Direction.Out), { CornerRadius = UDim.new(0.5, 20) })
track("G3.CornerRadius", corner, "CornerRadius")

local G4 = frame("G4", { Position = UDim2.new() })
create("G4", G4, TweenInfo.new(1.5, Style.Elastic, Direction.InOut), { Position = UDim2.new(1, -100, 0, 0) })
track("G4.Position", G4, "Position")

local H1 = frame("H1", { Position = UDim2.new() })
track("H1.Position", H1, "Position")
local H2 = frame("H2", { Size = UDim2.fromOffset(100, 100) })
track("H2.Size", H2, "Size")
local H3 = frame("H3", { Size = UDim2.fromOffset(100, 100), Position = UDim2.new() })
track("H3.Size", H3, "Size")
track("H3.Position", H3, "Position")
local H4 = frame("H4", { Size = UDim2.fromOffset(100, 100) })
track("H4.Size", H4, "Size")
local H5 = frame("H5", { Position = UDim2.new() })
track("H5.Position", H5, "Position")

for _, name in tweenNames do
	tweens[name]:Play()
end
local legacy = {
	H1 = H1:TweenPosition(UDim2.fromOffset(200, 0), Direction.Out, Style.Quad, 1, false, callback("H1")),
	H2 = H2:TweenSize(UDim2.fromOffset(50, 50)),
	H3 = H3:TweenSizeAndPosition(UDim2.fromOffset(150, 20), UDim2.fromOffset(40, 40), Direction.InOut, Style.Back, 1.2, false, callback("H3")),
	H4 = H4:TweenSize(UDim2.fromOffset(50, 50), Direction.Out, Style.Quad, 1),
	H5 = H5:TweenPosition(UDim2.fromOffset(200, 0)),
}
mainProbeTween:Play()

local actionProbes = {}
local function act(name, fn)
	local value, tween = probe()
	local result = fn()
	tween:Play()
	actionProbes[name] = value
	local e, clock = now()
	actions[#actions + 1] = { action = name, e = e, clock = clock, result = result }
end

local plan = {
	{ at = 0.3, name = "D:Pause", fn = function() tweens.D:Pause() end },
	{ at = 0.4, name = "F2:Play", fn = function()
		create("F2", F, TweenInfo.new(1, Style.Quad, Direction.InOut), { Position = UDim2.fromOffset(300, 0) }):Play()
	end },
	{ at = 0.5, name = "H1:TweenPosition(no override)", fn = function()
		return H1:TweenPosition(UDim2.fromOffset(0, 200), Direction.Out, Style.Quad, 1, false, callback("H1b"))
	end },
	{ at = 0.6, name = "E:Cancel", fn = function() tweens.E:Cancel() end },
	{ at = 0.6, name = "H1:TweenPosition(override)", fn = function()
		return H1:TweenPosition(UDim2.fromOffset(0, 200), Direction.In, Style.Linear, 0.5, true, callback("H1c"))
	end },
	{ at = 0.7, name = "D:Play", fn = function() tweens.D:Play() end },
	{ at = 0.9, name = "E:Play", fn = function() tweens.E:Play() end },
}

local samples = {}
local done = false
local connection
connection = RunService.Heartbeat:Connect(function(dt)
	local e, clock = now()
	for _, step in plan do
		if not step.done and e >= step.at then
			step.done = true
			act(step.name, step.fn)
		end
	end
	local values = {}
	for i, entry in tracks do
		values[i] = encode(entry.instance[entry.property])
	end
	local states = {}
	for name, tween in tweens do
		states[name] = tween.PlaybackState.Name
	end
	local probes = {}
	for name, value in actionProbes do
		probes[name] = value.Value
	end
	samples[#samples + 1] = { e = e, clock = clock, dt = dt, values = values, states = states, probes = probes }
	if e >= RECORD_S then
		connection:Disconnect()
		done = true
	end
end)
while not done do
	task.wait()
end

local trackNames = {}
for i, entry in tracks do
	trackNames[i] = entry.name
end
local out = {
	studioVersion = version(),
	tracks = trackNames,
	legacy = legacy,
	samples = samples,
	completions = completions,
	callbacks = events,
	actions = actions,
}
gui:Destroy()
local json = HttpService:JSONEncode(out)
local folder = Instance.new("Folder")
folder.Name = "RHRTweenRecordingOut"
local count = 0
for start = 1, #json, CHUNK do
	count += 1
	local chunk = Instance.new("StringValue")
	chunk.Name = tostring(count)
	chunk.Value = string.sub(json, start, start + CHUNK - 1)
	chunk.Parent = folder
end
folder.Parent = Players.LocalPlayer.PlayerGui
return count
