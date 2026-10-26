-- Tween edge cases as Roblox plays them, for tests/fixtures/tween/semantics.json: a
-- tween that takes over every property of a playing or paused one, Pause, Cancel and
-- Play while a tween waits out its delay, has not started or has completed, replays,
-- a destroyed tween, a negative Time, RepeatCount -2, value types beyond the GUI ones,
-- whole-number properties and a fractional goal for one (32- and 64-bit),
-- GuiObject.Transparency, setters that clamp an overshoot, booleans on curves that
-- leave 0..1, an empty goal table, zero-Time repeats, Pause and Play in one frame, a
-- legacy tween and a Tween on one property each way round, a property set after Play,
-- during a delay, before a repeat or on every frame across a delay's end, a legacy
-- tween that ends before those called after it, what Create, TweenInfo.new and the
-- legacy tweens refuse, and a legacy tween's callback when an override is refused.
--
-- Run it in Studio Play mode on the Server datamodel through the Studio MCP's
-- execute_luau (a client's tweens step only while its viewport renders). The JSON is
-- in the format of record_tween_trajectories.luau (tracks, samples every Heartbeat
-- against a clock probe, completions, callbacks and actions) plus `errors`, `infos`
-- and `setters`. It is longer than execute_luau returns in one call, so it is left in
-- StringValues under ReplicatedStorage.RHRTweenSemanticsOut, CHUNK characters each,
-- and the script returns how many there are; read them in order, then stop Play mode.

local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")

local RECORD_S = 1.3
local CHUNK = 60000

local folder = Instance.new("Folder")
folder.Name = "RHRTweenSemanticsRecording"
folder.Parent = ReplicatedStorage

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
	elseif kind == "Vector3" then
		return { value.X, value.Y, value.Z }
	elseif kind == "CFrame" then
		return { value:GetComponents() }
	elseif kind == "Rect" then
		return { value.Min.X, value.Min.Y, value.Max.X, value.Max.Y }
	elseif kind == "EnumItem" then
		return value.Name
	end
	return value
end

local function new(className, props)
	local instance = Instance.new(className)
	for key, value in props or {} do
		instance[key] = value
	end
	instance.Parent = folder
	return instance
end

local function probe()
	local value = new("NumberValue")
	return value, TweenService:Create(value, TweenInfo.new(100, Enum.EasingStyle.Linear), { Value = 100 })
end

local tracks = {}
local function track(name, instance, property)
	tracks[#tracks + 1] = { name = name, instance = instance, property = property }
end

local tweens, tweenNames = {}, {}
local completions, actions, callbacks = {}, {}, {}
local mainProbe, mainProbeTween = probe()

local function create(name, instance, info, goals)
	local tween = TweenService:Create(instance, info, goals)
	tweens[name] = tween
	tweenNames[#tweenNames + 1] = name
	tween.Completed:Connect(function(state)
		local at = {}
		for property in goals do
			at[property] = encode(instance[property])
		end
		completions[#completions + 1] = { tween = name, state = state.Name, e = mainProbe.Value, values = at }
	end)
	return tween
end

local Style, Direction = Enum.EasingStyle, Enum.EasingDirection
local function linear(time, delay)
	return TweenInfo.new(time, Style.Linear, Direction.In, 0, false, delay or 0)
end

-- Played in one block with the main probe.
local P = new("NumberValue")
create("P1", P, linear(1), { Value = 100 })
track("P.Value", P, "Value")

local T = new("NumberValue")
create("T1", T, linear(1), { Value = 100 })
track("T.Value", T, "Value")

local S = new("Frame")
create("S1", S, linear(1), { BackgroundTransparency = 1, Rotation = 100 })
track("S.Rotation", S, "Rotation")
track("S.BackgroundTransparency", S, "BackgroundTransparency")

local Q = new("NumberValue")
create("Q", Q, linear(0.2, 0.3), { Value = 10 })
track("Q.Value", Q, "Value")

local G = new("NumberValue")
create("G", G, linear(0.2, 0.3), { Value = 10 })
track("G.Value", G, "Value")

local B = new("NumberValue")
create("B", B, linear(1), { Value = 100 })
track("B.Value", B, "Value")

local F = new("NumberValue")
create("F", F, linear(0.2), { Value = 10 })
track("F.Value", F, "Value")

local Z = new("NumberValue")
create("Z", Z, linear(0), { Value = 7 })
track("Z.Value", Z, "Value")

local R = new("NumberValue")
create("R", R, linear(0.2), { Value = 10 })
track("R.Value", R, "Value")

local I = new("IntValue")
create("I", I, linear(1), { Value = 10 })
track("I.Value", I, "Value")

local V3 = new("Vector3Value")
create("V3", V3, TweenInfo.new(1, Style.Quad, Direction.Out), { Value = Vector3.new(10, -20, 30) })
track("V3.Value", V3, "Value")

local CF = new("CFrameValue")
create("CF", CF, linear(1), { Value = CFrame.new(10, 0, 0) * CFrame.Angles(0, math.pi / 2, 0) })
track("CF.Value", CF, "Value")

local C3 = new("Color3Value", { Value = Color3.new(1, 1, 0) })
create("C3", C3, linear(1), { Value = Color3.new(0, 0.5, 1) })
track("C3.Value", C3, "Value")

local BV = new("BoolValue", { Value = false })
create("BV", BV, linear(1), { Value = true })
track("BV.Value", BV, "Value")

local IMG = new("ImageLabel", { ImageTransparency = 0, SliceCenter = Rect.new(0, 0, 0, 0) })
create("IMG", IMG, TweenInfo.new(1, Style.Back, Direction.Out), { ImageTransparency = 1, SliceCenter = Rect.new(10, 10, 20, 20) })
track("IMG.ImageTransparency", IMG, "ImageTransparency")
track("IMG.SliceCenter", IMG, "SliceCenter")

local TXT = new("TextLabel", { TextSize = 90 })
create("TXT", TXT, TweenInfo.new(1, Style.Back, Direction.Out), { TextSize = 100 })
track("TXT.TextSize", TXT, "TextSize")

local PAD = new("UIPadding")
create("PAD", PAD, TweenInfo.new(1, Style.Quad, Direction.InOut), { PaddingLeft = UDim.new(0.5, 15) })
track("PAD.PaddingLeft", PAD, "PaddingLeft")

local DES = new("NumberValue")
create("DES", DES, linear(1), { Value = 100 })
track("DES.Value", DES, "Value")

local DLY = new("NumberValue")
create("DLY", DLY, linear(0.5, 0.3), { Value = 100 })
track("DLY.Value", DLY, "Value")

local PA = new("NumberValue")
create("PA", PA, linear(0.5), { Value = 100 })
track("PA.Value", PA, "Value")

local NEG = new("NumberValue")
create("NEG", NEG, TweenInfo.new(-1, Style.Linear, Direction.In), { Value = 7 })
track("NEG.Value", NEG, "Value")

local REP = new("NumberValue")
create("REP", REP, TweenInfo.new(0.2, Style.Linear, Direction.In, -2), { Value = 10 })
track("REP.Value", REP, "Value")

local CC = new("NumberValue")
create("CC", CC, linear(0.1), { Value = 5 })
track("CC.Value", CC, "Value")

-- Longer than the recording, so its Completed (which would read Transparency) never fires.
local TR = new("Frame", { BackgroundTransparency = 0 })
create("TR", TR, linear(2), { Transparency = 1 })
track("TR.BackgroundTransparency", TR, "BackgroundTransparency")

local INT = new("Frame", { BorderSizePixel = 0, LayoutOrder = 0 })
create("INT", INT, linear(1), { BorderSizePixel = 3, LayoutOrder = -3 })
track("INT.BorderSizePixel", INT, "BorderSizePixel")
track("INT.LayoutOrder", INT, "LayoutOrder")

local EMP = new("NumberValue")
create("EMP", EMP, linear(0.4), {})

-- Three that end on one frame, the first paused and played again at once.
local RA, RB, RC = new("NumberValue"), new("NumberValue"), new("NumberValue")
create("RA", RA, linear(0.5), { Value = 100 })
create("RB", RB, linear(0.5), { Value = 100 })
create("RC", RC, linear(0.5), { Value = 100 })
track("RA.Value", RA, "Value")

local BVB = new("BoolValue", { Value = false })
create("BVB", BVB, TweenInfo.new(1, Style.Back, Direction.In), { Value = true })
track("BVB.Value", BVB, "Value")
local BVO = new("BoolValue", { Value = true })
create("BVO", BVO, TweenInfo.new(1, Style.Back, Direction.Out), { Value = false })
track("BVO.Value", BVO, "Value")

local ZR = new("NumberValue")
create("ZR", ZR, TweenInfo.new(0, Style.Linear, Direction.In, 2, true), { Value = 7 })
track("ZR.Value", ZR, "Value")
local ZN = new("NumberValue")
create("ZN", ZN, TweenInfo.new(0, Style.Linear, Direction.In, 2, false), { Value = 7 })
track("ZN.Value", ZN, "Value")

local INT2 = new("Frame", { BorderSizePixel = 0, LayoutOrder = 0 })
create("INT2", INT2, linear(0.3), { BorderSizePixel = 2.7, LayoutOrder = -2.7 })
track("INT2.BorderSizePixel", INT2, "BorderSizePixel")
track("INT2.LayoutOrder", INT2, "LayoutOrder")

-- Set after Play before any step, during a delay, and during the delay before a repeat.
local SN = new("NumberValue")
create("SN", SN, linear(0.4), { Value = 100 })
track("SN.Value", SN, "Value")
local SD = new("NumberValue")
create("SD", SD, linear(0.4, 0.2), { Value = 100 })
track("SD.Value", SD, "Value")
local SR = new("NumberValue")
create("SR", SR, TweenInfo.new(0.2, Style.Linear, Direction.In, 1, false, 0.2), { Value = 100 })
track("SR.Value", SR, "Value")

-- A fractional goal for a 64-bit whole number, each side of a half. Create may refuse
-- one, so a refusal leaves its track out rather than ending the recording.
for _, case in { { "I64A", 2.7 }, { "I64B", -2.5 }, { "I64C", 2.5 } } do
	local value = new("IntValue")
	if pcall(create, case[1], value, linear(0.6), { Value = case[2] }) then
		track(case[1] .. ".Value", value, "Value")
	end
end

-- Heartbeat writes the sample count into DC after each sample, so the value its tween
-- starts from names the step it read it on: the step its delay ends, or the next.
local DC = new("NumberValue")
create("DC", DC, linear(100, 0.2), { Value = -1000 })
track("DC.Value", DC, "Value")

local LB = new("Frame", { Position = UDim2.new() })
track("LB.Position", LB, "Position")
local LT = new("Frame", { Position = UDim2.new() })
track("LT.Position", LT, "Position")
local TL = new("Frame", { Position = UDim2.new() })
track("TL.Position", TL, "Position")
local LG = new("Frame", { Position = UDim2.new() })
track("LG.Position", LG, "Position")
-- The first called ends first; the other three end on one frame, so the order of their
-- callbacks tells where the first one's place in the queue went.
local LQ = {}
for i = 1, 4 do
	LQ[i] = new("Frame", { Position = UDim2.new() })
end
local function callback(name)
	return function(status)
		callbacks[#callbacks + 1] = { callback = name, status = status.Name, e = mainProbe.Value }
	end
end

for _, name in tweenNames do
	if name ~= "R" then
		tweens[name]:Play()
	end
end
mainProbeTween:Play()
LB:TweenPosition(UDim2.fromOffset(200, 0), Direction.Out, Style.Linear, 1, false, callback("LB"))
LT:TweenPosition(UDim2.fromOffset(100, 0), Direction.Out, Style.Linear, 1, false, callback("LT"))
create("LTS", LT, linear(1), { Position = UDim2.fromOffset(0, 100) }):Play()
create("TLS", TL, linear(1), { Position = UDim2.fromOffset(0, 100) }):Play()
TL:TweenPosition(UDim2.fromOffset(100, 0), Direction.Out, Style.Linear, 1, false, callback("TL"))
LG:TweenPosition(UDim2.fromOffset(100, 0), Direction.Out, Style.Linear, 0.5, false, callback("LG"))
for i, frame in LQ do
	frame:TweenPosition(UDim2.fromOffset(100, 0), Direction.Out, Style.Linear, if i == 1 then 0.1 else 0.4, false,
		callback(`LQ{i}`))
end
SN.Value = 40
LG.Position = UDim2.fromOffset(0, 40)

-- What Create and TweenInfo.new refuse, and what TweenInfo.new keeps.
local errors = {}
for _, case in {
	{ "string property", function() TweenService:Create(new("Frame"), linear(1), { Name = "x" }) end },
	{ "enum property", function() TweenService:Create(new("Frame"), linear(1), { AutomaticSize = Enum.AutomaticSize.X }) end },
	{ "missing property", function() TweenService:Create(new("Frame"), linear(1), { Nope = 1 }) end },
	{ "type mismatch", function() TweenService:Create(new("Frame"), linear(1), { Rotation = "x" }) end },
	{ "no instance", function() TweenService:Create(nil, linear(1), { Value = 1 }) end },
	{ "Bezier", function() TweenInfo.new(1, Style.Bezier) end },
	{ "GetValue Spring", function() TweenService:GetValue(0.5, Style.Spring, Direction.In) end },
	{ "legacy tween outside the data model", function() Instance.new("Frame"):TweenPosition(UDim2.new()) end },
	{ "fractional int64 goal", function() TweenService:Create(new("IntValue"), linear(1), { Value = 2.5 }) end },
} do
	local ok, problem = pcall(case[2])
	errors[#errors + 1] = { case = case[1], ok = ok, error = if ok then nil else tostring(problem) }
end
local infos = {}
for _, case in {
	{ "no arguments", function() return TweenInfo.new() end },
	{ "negative time", function() return TweenInfo.new(-1) end },
	{ "negative delay", function() return TweenInfo.new(1, Style.Linear, Direction.In, 0, false, -1) end },
	{ "repeat -2", function() return TweenInfo.new(1, Style.Linear, Direction.In, -2) end },
	{ "repeat 1.5", function() return TweenInfo.new(1, Style.Linear, Direction.In, 1.5) end },
} do
	local ok, info = pcall(case[2])
	infos[#infos + 1] = if ok
		then { case = case[1], Time = info.Time, EasingStyle = info.EasingStyle.Name, EasingDirection = info.EasingDirection.Name,
			RepeatCount = info.RepeatCount, Reverses = info.Reverses, DelayTime = info.DelayTime }
		else { case = case[1], error = tostring(info) }
end

-- Setters a tween writes through that round, truncate or clamp what they are given,
-- beside those in record_tween_legacy.luau.
local setters = {}
for _, case in {
	{ "TextLabel", "TextSize", 15.7 },
	{ "TextLabel", "TextSize", 99.9 },
	{ "TextLabel", "TextSize", -5 },
	{ "TextButton", "TextSize", 15.7 },
	{ "TextBox", "TextSize", 15.7 },
	{ "TextLabel", "LineHeight", -1 },
	{ "TextLabel", "MaxVisibleGraphemes", 2.7 },
	{ "IntValue", "Value", 2.5 },
	{ "IntValue", "Value", -2.5 },
	{ "IntValue", "Value", 2.7 },
	{ "Frame", "ZIndex", 2.7 },
	{ "Frame", "ZIndex", -2.7 },
	{ "Frame", "LayoutOrder", 2.7 },
	{ "Frame", "BorderSizePixel", 2.7 },
	{ "ScrollingFrame", "ScrollBarThickness", 2.7 },
	{ "UIScale", "Scale", 0 },
	{ "UIStroke", "Thickness", 1.37 },
} do
	local instance = Instance.new(case[1])
	local ok, problem = pcall(function()
		instance[case[2]] = case[3]
	end)
	setters[#setters + 1] = { class = case[1], property = case[2], set = case[3],
		read = if ok then instance[case[2]] else nil, error = if ok then nil else tostring(problem) }
	instance:Destroy()
end

-- An action's probe plays just before it, after what the action only prepares, so a
-- tween the action plays starts within a Play call of its probe.
local actionProbes = {}
local function act(step)
	local value, tween = probe()
	local prepared = if step.prepare then step.prepare() else nil
	tween:Play()
	local result = step.fn(prepared)
	actionProbes[step.name] = value
	actions[#actions + 1] = { action = step.name, e = mainProbe.Value, result = result }
end
local function play(tween)
	tween:Play()
end

local plan = {
	{ at = 0.05, name = "R:Pause+Cancel(Begin)", fn = function()
		tweens.R:Pause()
		tweens.R:Cancel()
		return tweens.R.PlaybackState.Name
	end },
	{ at = 0.1, name = "Q:Cancel(delay)", fn = function() tweens.Q:Cancel() end },
	{ at = 0.1, name = "G:Pause(delay)", fn = function() tweens.G:Pause() return tweens.G.PlaybackState.Name end },
	{ at = 0.2, name = "Q:Play(after cancel)", fn = function() tweens.Q:Play() end },
	{ at = 0.1, name = "DES:Destroy", fn = function()
		tweens.DES:Destroy()
		tweens.DES = nil
	end },
	{ at = 0.1, name = "DLY:Destroy(delay)", fn = function()
		tweens.DLY:Destroy()
		tweens.DLY = nil
	end },
	{ at = 0.1, name = "SD:set(delay)", fn = function()
		SD.Value = 50
	end },
	{ at = 0.5, name = "SR:set(repeat delay)", fn = function()
		SR.Value = 30
	end },
	{ at = 0.2, name = "PA:Pause", fn = function()
		tweens.PA:Pause()
		return tweens.PA.PlaybackState.Name
	end },
	{ at = 0.2, name = "RA:Pause+Play", fn = function()
		tweens.RA:Pause()
		tweens.RA:Play()
		return tweens.RA.PlaybackState.Name
	end },
	{ at = 0.3, name = "P2:Play(delayed takeover)", prepare = function()
		return create("P2", P, linear(0.2, 0.3), { Value = 500 })
	end, fn = play },
	{ at = 0.3, name = "T2:Play(takeover)", prepare = function()
		return create("T2", T, linear(0.3), { Value = 500 })
	end, fn = play },
	{ at = 0.3, name = "S2:Play(partial takeover)", prepare = function()
		return create("S2", S, linear(0.2), { Rotation = -50 })
	end, fn = play },
	{ at = 0.3, name = "PB:Play(takeover of paused)", prepare = function()
		return create("PB", PA, linear(0.2), { Value = -50 })
	end, fn = play },
	{ at = 0.3, name = "LB:TweenPosition(bad style, override)", fn = function()
		local ok, problem = pcall(function()
			return LB:TweenPosition(UDim2.new(), Direction.Out, "Bogus", 1, true, callback("LB2"))
		end)
		return if ok then tostring(problem) else problem
	end },
	{ at = 0.4, name = "B:Play(playing)", fn = function() tweens.B:Play() end },
	{ at = 0.5, name = "F:set+Play(completed)", fn = function()
		F.Value = 50
		tweens.F:Play()
	end },
	{ at = 0.6, name = "G:Play(completed)", fn = function() tweens.G:Play() end },
	{ at = 0.6, name = "CC:Cancel(completed)", fn = function()
		tweens.CC:Cancel()
		return tweens.CC.PlaybackState.Name
	end },
	{ at = 0.7, name = "R:Play", fn = function() tweens.R:Play() end },
	{ at = 0.7, name = "PA:Play(cancelled by a takeover)", fn = function()
		local before = tweens.PA.PlaybackState.Name
		tweens.PA:Play()
		return before
	end },
}

local samples = {}
local done = false
local connection = RunService.Heartbeat:Connect(function(dt)
	local e = mainProbe.Value
	for _, step in plan do
		if not step.done and e >= step.at then
			step.done = true
			act(step)
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
	samples[#samples + 1] = { e = e, dt = dt, values = values, states = states, probes = probes }
	DC.Value = #samples
	if e >= RECORD_S then
		done = true
	end
end)
while not done do
	task.wait()
end
connection:Disconnect()
folder:Destroy()

local trackNames = {}
for i, entry in tracks do
	trackNames[i] = entry.name
end
local json = HttpService:JSONEncode({
	studioVersion = version(),
	tracks = trackNames,
	samples = samples,
	completions = completions,
	callbacks = callbacks,
	actions = actions,
	errors = errors,
	infos = infos,
	setters = setters,
})
-- A second run in one Play would otherwise leave the first run's chunks found first.
local stale = ReplicatedStorage:FindFirstChild("RHRTweenSemanticsOut")
if stale then
	stale:Destroy()
end
local out = Instance.new("Folder")
out.Name = "RHRTweenSemanticsOut"
local count = 0
for start = 1, #json, CHUNK do
	count += 1
	local chunk = Instance.new("StringValue")
	chunk.Name = tostring(count)
	chunk.Value = string.sub(json, start, start + CHUNK - 1)
	chunk.Parent = out
end
out.Parent = ReplicatedStorage
return count
