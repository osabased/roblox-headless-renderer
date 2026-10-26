-- Replays Studio's tween recordings (tests/fixtures/tween/, made by
-- scripts/studio/record_tween_*.luau) against RHR's tweens (src/rhr/luau/tween.luau) and
-- prints what RHR gives, as JSON, for tests/test_tween.py to compare.
--
--   lune run tests/tween_replay.luau <fixtures dir> [shift]
--
-- Each recording's instances, tweens and actions are rebuilt as its script makes them,
-- and the clock is set to each sample's time before the tweens step. Studio's clock
-- probes read up to 3 us off (a 100 s tween's progress is rounded to about 2^-25 of its
-- length), so times come from all of their readings rather than one: an action runs at
-- its own probe's start, averaged over every sample. A Server steps its tweens by
-- Heartbeat's dt, so in a Server's recording a sample's time is the dt summed since the
-- first sample, from a start averaged the same way; a client steps them on its render
-- clock, so in a client's recording it is the main probe's reading.
--
-- With a shift (seconds), only the client's recording is replayed, each sample read that
-- much later, actions where they were: a value Studio rounded near a half pixel can be
-- read on the other side of it within the probe's error.
local fs = require("@lune/fs")
local process = require("@lune/process")
local roblox = require("@lune/roblox")
local serde = require("@lune/serde")

local Enum = roblox.Enum
local Instance, TweenInfo = roblox.Instance, nil
local UDim, UDim2, Vector2, Vector3, Color3, CFrame, Rect =
	roblox.UDim, roblox.UDim2, roblox.Vector2, roblox.Vector3, roblox.Color3, roblox.CFrame, roblox.Rect

local clock = 0
local shift = tonumber(process.args[2])
local Signal = {}
Signal.__index = Signal
function Signal:Connect(fn)
	table.insert(self.handlers, fn)
end
function Signal:Fire(...)
	for _, fn in table.clone(self.handlers) do
		fn(...)
	end
end
local signals = {}
local function event(instance, name)
	local byName = signals[instance]
	if not byName then
		byName = {}
		signals[instance] = byName
	end
	byName[name] = byName[name] or setmetatable({ handlers = {} }, Signal)
	return byName[name]
end

-- The recordings' instances sit in a data model, as legacy tweens need.
local world = Instance.new("DataModel")
local tweens = require("../src/rhr/luau/tween")({
	now = function()
		return clock
	end,
	event = event,
	spawn = function(fn, ...)
		fn(...)
	end,
	inGame = function(instance)
		return instance:IsDescendantOf(world)
	end,
})
TweenInfo = tweens.TweenInfo
local TweenService = world:GetService("TweenService")
local storage = world:GetService("ReplicatedStorage")
local Style, Direction = Enum.EasingStyle, Enum.EasingDirection

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

local function read(path)
	return serde.decode("json", fs.readFile(path))
end

-- A recording's tweens, tracks, completions and the replay loop shared by its scripts. An
-- action's clock probe plays after the action with `probeAfter`, else just before it.
local function recording(probeAfter)
	local self = { tracks = {}, tweens = {}, order = {}, completions = {}, callbacks = {}, actions = {} }
	-- The clock probes are tweens in Roblox's queue with the rest, so they play here too,
	-- where the recording played them: where one sits changes the order tweens step in.
	function self.probe()
		local value = Instance.new("NumberValue")
		value.Parent = storage
		TweenService:Create(value, TweenInfo.new(100, Style.Linear), { Value = 100 }):Play()
	end
	function self.track(name, instance, property)
		table.insert(self.tracks, { name = name, instance = instance, property = property })
	end
	function self.create(name, instance, info, goals)
		local tween = TweenService:Create(instance, info, goals)
		self.tweens[name] = tween
		table.insert(self.order, name)
		tween.Completed:Connect(function(state)
			local at = {}
			for property in goals do
				at[property] = encode(instance[property])
			end
			table.insert(self.completions, { tween = name, state = state.Name, e = clock, values = at })
		end)
		return tween
	end
	function self.callback(name)
		return function(status)
			table.insert(self.callbacks, { callback = name, status = status.Name, e = clock })
		end
	end
	function self.replay(samples, plan, server)
		local times = {}
		local since, offset = 0, 0
		for index, sample in samples do
			since += if index > 1 then sample.dt else 0
			times[index] = if server then since else sample.e
			offset += sample.e - times[index]
		end
		for index in times do
			times[index] += offset / #samples
		end
		local starts, counts = {}, {}
		for index, sample in samples do
			for name, elapsed in sample.probes do
				if elapsed > 0 then
					starts[name] = (starts[name] or 0) + times[index] - elapsed
					counts[name] = (counts[name] or 0) + 1
				end
			end
		end
		local out = {}
		for index, sample in samples do
			clock = times[index] + (shift or 0)
			tweens.step()
			for _, step in plan do
				if not step.done and sample.e >= step.at then
					step.done = true
					clock = if starts[step.name] then starts[step.name] / counts[step.name] else times[index]
					local prepared = if step.prepare then step.prepare() else nil
					if not probeAfter then
						self.probe()
					end
					local result = step.fn(prepared)
					if probeAfter then
						self.probe()
					end
					table.insert(self.actions, { action = step.name, e = clock, result = result })
					clock = times[index] + (shift or 0)
				end
			end
			local values, states = {}, {}
			for i, entry in self.tracks do
				values[i] = encode(entry.instance[entry.property])
			end
			for name, tween in self.tweens do
				states[name] = tween.PlaybackState.Name
			end
			out[index] = { e = sample.e, values = values, states = states }
		end
		local names = {}
		for i, entry in self.tracks do
			names[i] = entry.name
		end
		return { tracks = names, samples = out, completions = self.completions, callbacks = self.callbacks,
			actions = self.actions }
	end
	return self
end

-- TweenService:GetValue --------------------------------------------------------------------
local function getValue(data)
	local function curve(alphas, style, direction)
		local list = {}
		for i, alpha in alphas do
			list[i] = TweenService:GetValue(alpha, Style[style], Direction[direction])
		end
		return list
	end
	local values, extra = {}, {}
	for style, byDirection in data.values do
		values[style], extra[style] = {}, {}
		for direction in byDirection do
			values[style][direction] = curve(data.alphas, style, direction)
			extra[style][direction] = curve(data.extraAlphas, style, direction)
		end
	end
	return { values = values, extra = extra }
end

-- record_tween_trajectories.luau ------------------------------------------------------------
local function trajectories(data)
	local r = recording(true)
	local gui = Instance.new("ScreenGui")
	gui.Parent = storage
	local function frame(name, props)
		local instance = Instance.new("Frame")
		instance.Name = name
		for key, value in props do
			instance[key] = value
		end
		instance.Parent = gui
		return instance
	end
	local create, track = r.create, r.track

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

	for _, name in r.order do
		r.tweens[name]:Play()
	end
	local callback = r.callback
	local legacy = {
		H1 = H1:TweenPosition(UDim2.fromOffset(200, 0), Direction.Out, Style.Quad, 1, false, callback("H1")),
		H2 = H2:TweenSize(UDim2.fromOffset(50, 50)),
		H3 = H3:TweenSizeAndPosition(UDim2.fromOffset(150, 20), UDim2.fromOffset(40, 40), Direction.InOut, Style.Back,
			1.2, false, callback("H3")),
		H4 = H4:TweenSize(UDim2.fromOffset(50, 50), Direction.Out, Style.Quad, 1),
		H5 = H5:TweenPosition(UDim2.fromOffset(200, 0)),
	}
	r.probe()
	local result = r.replay(data.samples, {
		{ at = 0.3, name = "D:Pause", fn = function()
			r.tweens.D:Pause()
		end },
		{ at = 0.4, name = "F2:Play", fn = function()
			create("F2", F, TweenInfo.new(1, Style.Quad, Direction.InOut), { Position = UDim2.fromOffset(300, 0) }):Play()
		end },
		{ at = 0.5, name = "H1:TweenPosition(no override)", fn = function()
			return H1:TweenPosition(UDim2.fromOffset(0, 200), Direction.Out, Style.Quad, 1, false, callback("H1b"))
		end },
		{ at = 0.6, name = "E:Cancel", fn = function()
			r.tweens.E:Cancel()
		end },
		{ at = 0.6, name = "H1:TweenPosition(override)", fn = function()
			return H1:TweenPosition(UDim2.fromOffset(0, 200), Direction.In, Style.Linear, 0.5, true, callback("H1c"))
		end },
		{ at = 0.7, name = "D:Play", fn = function()
			r.tweens.D:Play()
		end },
		{ at = 0.9, name = "E:Play", fn = function()
			r.tweens.E:Play()
		end },
	})
	result.legacy = legacy
	return result
end

-- A value a tween writes, read back: through a zero-time tween, so the setter rules a
-- tween's writes go through apply.
local reflection = roblox.getReflectionDatabase()
local function datatype(className, property)
	local class = reflection:FindClass(className)
	while class do
		local found = class.Properties[property]
		if found then
			return found.Datatype
		end
		class = class.Superclass and reflection:FindClass(class.Superclass)
	end
	return nil
end
local function setters(cases)
	local out = {}
	for i, case in cases do
		local instance = Instance.new(case.class)
		local value = case.set
		local kind = datatype(case.class, case.property)
		if kind == "Vector2" then
			value = Vector2.new(value[1], value[2])
		elseif kind == "Color3" then
			value = Color3.new(value[1], value[2], value[3])
		elseif kind == "UDim" then
			value = UDim.new(value[1], value[2])
		end
		local ok, problem = pcall(function()
			TweenService:Create(instance, TweenInfo.new(0), { [case.property] = value }):Play()
			tweens.step()
		end)
		out[i] = if ok then { read = encode(instance[case.property]) } else { error = tostring(problem) }
	end
	return out
end

-- record_tween_legacy.luau ------------------------------------------------------------------
local function legacyCurves(data)
	clock = 0
	local gui = Instance.new("ScreenGui")
	gui.Parent = storage
	local frames, times = {}, {}
	for key, list in data.curves do
		local style, direction = string.match(key, "^(%w+)%.(%w+)$")
		local frame = Instance.new("Frame")
		frame.Parent = gui
		frames[key] = frame
		frame:TweenPosition(UDim2.new(1, 0, 0, 0), Direction[direction], Style[style], data.duration)
		if #times == 0 then
			for i, sample in list do
				times[i] = tonumber(string.match(sample, "^(%S+)"))
			end
		end
	end
	local curves = {}
	for key in frames do
		curves[key] = {}
	end
	for i, e in times do
		clock = e
		tweens.step()
		for key, frame in frames do
			curves[key][i] = frame.Position.X.Scale
		end
	end
	return { times = times, curves = curves, setters = setters(data.setters) }
end

-- record_tween_semantics.luau ---------------------------------------------------------------
local function semantics(data)
	clock = 0
	local r = recording()
	local folder = Instance.new("Folder")
	folder.Parent = storage
	local function new(className, props)
		local instance = Instance.new(className)
		for key, value in props or {} do
			instance[key] = value
		end
		instance.Parent = folder
		return instance
	end
	local create, track = r.create, r.track
	local function linear(time, delay)
		return TweenInfo.new(time, Style.Linear, Direction.In, 0, false, delay or 0)
	end
	local function play(tween)
		tween:Play()
	end

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
	create("IMG", IMG, TweenInfo.new(1, Style.Back, Direction.Out), { ImageTransparency = 1,
		SliceCenter = Rect.new(10, 10, 20, 20) })
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
	local TR = new("Frame", { BackgroundTransparency = 0 })
	create("TR", TR, linear(2), { Transparency = 1 })
	track("TR.BackgroundTransparency", TR, "BackgroundTransparency")
	local INT = new("Frame", { BorderSizePixel = 0, LayoutOrder = 0 })
	create("INT", INT, linear(1), { BorderSizePixel = 3, LayoutOrder = -3 })
	track("INT.BorderSizePixel", INT, "BorderSizePixel")
	track("INT.LayoutOrder", INT, "LayoutOrder")
	local LB = new("Frame", { Position = UDim2.new() })
	track("LB.Position", LB, "Position")

	for _, name in r.order do
		if name ~= "R" then
			r.tweens[name]:Play()
		end
	end
	r.probe()
	LB:TweenPosition(UDim2.fromOffset(200, 0), Direction.Out, Style.Linear, 1, false, r.callback("LB"))

	local errors = {}
	for _, case in {
		{ "string property", function() TweenService:Create(new("Frame"), linear(1), { Name = "x" }) end },
		{ "enum property", function() TweenService:Create(new("Frame"), linear(1), { AutomaticSize = Enum.AutomaticSize.X }) end },
		{ "missing property", function() TweenService:Create(new("Frame"), linear(1), { Nope = 1 }) end },
		{ "type mismatch", function() TweenService:Create(new("Frame"), linear(1), { Rotation = "x" }) end },
		{ "no instance", function() TweenService:Create(nil, linear(1), { Value = 1 }) end },
		-- Lune's Enum has neither style, so by name.
		{ "Bezier", function() TweenInfo.new(1, "Bezier") end },
		{ "GetValue Spring", function() TweenService:GetValue(0.5, "Spring", Direction.In) end },
		{ "legacy tween outside the data model", function() Instance.new("Frame"):TweenPosition(UDim2.new()) end },
	} do
		local ok, problem = pcall(case[2])
		table.insert(errors, { case = case[1], ok = ok, error = if ok then nil else tostring(problem) })
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
		table.insert(infos, if ok
			then { case = case[1], Time = info.Time, EasingStyle = info.EasingStyle.Name,
				EasingDirection = info.EasingDirection.Name, RepeatCount = info.RepeatCount, Reverses = info.Reverses,
				DelayTime = info.DelayTime }
			else { case = case[1], error = tostring(info) })
	end

	local result = r.replay(data.samples, {
		{ at = 0.05, name = "R:Pause+Cancel(Begin)", fn = function()
			r.tweens.R:Pause()
			r.tweens.R:Cancel()
			return r.tweens.R.PlaybackState.Name
		end },
		{ at = 0.1, name = "Q:Cancel(delay)", fn = function()
			r.tweens.Q:Cancel()
		end },
		{ at = 0.1, name = "G:Pause(delay)", fn = function()
			r.tweens.G:Pause()
			return r.tweens.G.PlaybackState.Name
		end },
		{ at = 0.2, name = "Q:Play(after cancel)", fn = function()
			r.tweens.Q:Play()
		end },
		{ at = 0.1, name = "DES:Destroy", fn = function()
			r.tweens.DES:Destroy()
			r.tweens.DES = nil
		end },
		{ at = 0.1, name = "DLY:Destroy(delay)", fn = function()
			r.tweens.DLY:Destroy()
			r.tweens.DLY = nil
		end },
		{ at = 0.2, name = "PA:Pause", fn = function()
			r.tweens.PA:Pause()
			return r.tweens.PA.PlaybackState.Name
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
				return LB:TweenPosition(UDim2.new(), Direction.Out, "Bogus", 1, true, r.callback("LB2"))
			end)
			return if ok then tostring(problem) else problem
		end },
		{ at = 0.4, name = "B:Play(playing)", fn = function()
			r.tweens.B:Play()
		end },
		{ at = 0.5, name = "F:set+Play(completed)", fn = function()
			F.Value = 50
			r.tweens.F:Play()
		end },
		{ at = 0.6, name = "G:Play(completed)", fn = function()
			r.tweens.G:Play()
		end },
		{ at = 0.6, name = "CC:Cancel(completed)", fn = function()
			r.tweens.CC:Cancel()
			return r.tweens.CC.PlaybackState.Name
		end },
		{ at = 0.7, name = "R:Play", fn = function()
			r.tweens.R:Play()
		end },
		{ at = 0.7, name = "PA:Play(cancelled by a takeover)", fn = function()
			local before = r.tweens.PA.PlaybackState.Name
			r.tweens.PA:Play()
			return before
		end },
	}, true)
	result.errors = errors
	result.infos = infos
	result.setters = setters(data.setters)
	return result
end

local dir = process.args[1] or "tests/fixtures/tween"
if shift then
	print(serde.encode("json", { trajectories = trajectories(read(dir .. "/trajectories.json")) }))
else
	print(serde.encode("json", {
		getvalue = getValue(read(dir .. "/getvalue.json")),
		trajectories = trajectories(read(dir .. "/trajectories.json")),
		legacy = legacyCurves(read(dir .. "/legacy.json")),
		semantics = semantics(read(dir .. "/semantics.json")),
	}))
end
