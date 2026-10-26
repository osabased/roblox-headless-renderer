-- TweenService, TweenInfo and GuiObject's legacy tweens on a clock the caller steps
-- (story time in story-runtime.luau). tests/test_tween.py replays recordings of Studio
-- 0.744 (tests/fixtures/tween/, made by scripts/studio/record_tween_*.luau) against it.
--
--   local tweens = require("./tween")(hooks)
--
-- hooks.now() is the time in seconds; hooks.event(instance, name) the instance's signal
-- of that name, with Fire; hooks.changed(instance, property) runs after a tween writes a
-- new value; hooks.spawn(fn, ...) runs a legacy tween's callback; hooks.inGame(instance)
-- says whether a legacy tween may play on it. step() moves every playing tween to
-- hooks.now(), once a frame (where in Roblox's frame it does is not measured); moving()
-- lists the tweens still playing or waiting out a delay.
local roblox = require("@lune/roblox")

local Enum = roblox.Enum
local CFrame, Color3, Rect, UDim, UDim2, Vector2, Vector3 =
	roblox.CFrame, roblox.Color3, roblox.Rect, roblox.UDim, roblox.UDim2, roblox.Vector2, roblox.Vector3

-- Easing ------------------------------------------------------------------------------
-- Each style is its In and Out curve; InOut joins the In curve's first half to the Out
-- curve's second. These match TweenService:GetValue to 4.2e-7 (getvalue.json).
local BACK = 1.70158
local function power(n)
	return { function(t)
		return t ^ n
	end, function(t)
		return 1 - (1 - t) ^ n
	end }
end
local function bounceOut(t)
	if t < 1 / 2.75 then
		return 7.5625 * t * t
	elseif t < 2 / 2.75 then
		t -= 1.5 / 2.75
		return 7.5625 * t * t + 0.75
	elseif t < 2.5 / 2.75 then
		t -= 2.25 / 2.75
		return 7.5625 * t * t + 0.9375
	end
	t -= 2.625 / 2.75
	return 7.5625 * t * t + 0.984375
end
local function elasticOut(t)
	if t == 0 or t == 1 then
		return t
	end
	return 1 - 2 ^ (-10 * t) * math.cos(6.5 * math.pi * t)
end
local function flipped(out)
	return function(t)
		return 1 - out(1 - t)
	end
end

local STYLES = {
	Linear = { function(t)
		return t
	end, function(t)
		return t
	end },
	Sine = { function(t)
		return 1 - math.cos(t * math.pi / 2)
	end, function(t)
		return math.sin(t * math.pi / 2)
	end },
	Quad = power(2),
	Cubic = power(3),
	Quart = power(4),
	Quint = power(5),
	Exponential = { function(t)
		return if t == 0 then 0 else 2 ^ (10 * t - 10)
	end, function(t)
		return if t == 1 then 1 else 1 - 2 ^ (-10 * t)
	end },
	Circular = { function(t)
		return 1 - math.sqrt(1 - t * t)
	end, function(t)
		return math.sqrt(1 - (t - 1) ^ 2)
	end },
	Back = { function(t)
		return t * t * ((BACK + 1) * t - BACK)
	end, function(t)
		return 1 + (BACK + 1) * (t - 1) ^ 3 + BACK * (t - 1) ^ 2
	end },
	Bounce = { flipped(bounceOut), bounceOut },
	Elastic = { flipped(elasticOut), elasticOut },
}

local function ease(curves, direction, t)
	if direction == "In" then
		return curves[1](t)
	elseif direction == "Out" then
		return curves[2](t)
	end
	return if t < 0.5 then curves[1](2 * t) / 2 else (1 + curves[2](2 * t - 1)) / 2
end

-- GuiObject:TweenPosition and the like keep older curves where they differ: Penner's
-- Elastic (period 0.3, and 0.45 for InOut), a Back InOut that ends on s/10 where
-- Penner's has s, and Exponential, Circular and Cubic, which hold the start until the
-- end and then jump to the goal (legacy.json).
local LEGACY_BACK = BACK * 1.525
local function legacyElasticOut(t)
	return 2 ^ (-10 * t) * math.sin((t - 0.075) * 2 * math.pi / 0.3) + 1
end
local function legacyElasticInOut(x)
	local t = 2 * x - 1
	if t < 0 then
		return -0.5 * 2 ^ (10 * t) * math.sin((t - 0.1125) * 2 * math.pi / 0.45)
	end
	return 2 ^ (-10 * t) * math.sin((t - 0.1125) * 2 * math.pi / 0.45) * 0.5 + 1
end
local function legacyBackInOut(x)
	local t = 2 * x
	if t < 1 then
		return t * t * ((LEGACY_BACK + 1) * t - LEGACY_BACK) / 2
	end
	local u = t - 2
	return (u * u * ((LEGACY_BACK + 1) * u + LEGACY_BACK / 10) + 2) / 2
end
local HOLDS = { Exponential = true, Circular = true, Cubic = true }

local function legacyEase(style, direction, t)
	if HOLDS[style] then
		return 0
	elseif style == "Elastic" then
		if direction == "InOut" then
			return legacyElasticInOut(t)
		end
		return ease({ flipped(legacyElasticOut), legacyElasticOut }, direction, t)
	elseif style == "Back" and direction == "InOut" then
		return legacyBackInOut(t)
	end
	return ease(STYLES[style], direction, t)
end

-- Enums -------------------------------------------------------------------------------
local UNSUPPORTED = { Bezier = true, Spring = true }

-- An EnumItem of `enum`, or its name or number, as Roblox takes enum arguments.
local function enumItem(enum, value, fallback, what)
	if value == nil then
		return fallback
	end
	local name = if typeof(value) == "EnumItem" then value.Name else value
	if UNSUPPORTED[name] and enum == Enum.EasingStyle then
		error(`{what} does not support Enum.EasingStyle.Spring or Enum.EasingStyle.Bezier`, 0)
	end
	for _, item in enum:GetEnumItems() do
		if item == value or item.Name == name or item.Value == value then
			return item
		end
	end
	error(`{what}: {tostring(value)} is not a valid {tostring(enum)}`, 0)
end

-- A legacy tween's enum argument: a name Roblox does not know is refused as it refuses
-- it (semantics.json).
local function castEnum(enum, value, fallback, enumName)
	if type(value) == "string" then
		local known = false
		for _, item in enum:GetEnumItems() do
			known = known or item.Name == value
		end
		if not known then
			error(`Unable to cast string to {enumName}`, 0)
		end
	end
	return enumItem(enum, value, fallback, "GuiObject tween")
end

-- TweenInfo -----------------------------------------------------------------------------
-- TweenInfo.new keeps what it is given, a negative Time or DelayTime and a RepeatCount
-- below -1 included, and drops a RepeatCount's fraction (semantics.json).
local infoMeta = {
	__type = "TweenInfo",
	__index = function(_, key)
		error(`{tostring(key)} is not a valid member of TweenInfo`, 2)
	end,
	__newindex = function(_, key)
		error(`{tostring(key)} cannot be assigned to`, 2)
	end,
	__tostring = function(info)
		return `Time:{info.Time} DelayTime:{info.DelayTime} RepeatCount:{info.RepeatCount} `
			.. `Reverses:{if info.Reverses then "True" else "False"} EasingDirection:{info.EasingDirection.Name} `
			.. `EasingStyle:{info.EasingStyle.Name}`
	end,
}
infoMeta.__eq = function(a, b)
	return a.Time == b.Time and a.DelayTime == b.DelayTime and a.RepeatCount == b.RepeatCount
		and a.Reverses == b.Reverses and a.EasingStyle == b.EasingStyle and a.EasingDirection == b.EasingDirection
end

local function number(value, fallback, index)
	if value == nil then
		return fallback
	end
	if type(value) ~= "number" then
		error(`invalid argument #{index} to 'new' (number expected, got {typeof(value)})`, 0)
	end
	return value
end

local TweenInfo = {}
function TweenInfo.new(time, style, direction, repeatCount, reverses, delayTime)
	if reverses ~= nil and type(reverses) ~= "boolean" then
		error(`invalid argument #5 to 'new' (boolean expected, got {typeof(reverses)})`, 0)
	end
	local repeats = number(repeatCount, 0, 4)
	return setmetatable({
		Time = number(time, 1, 1),
		EasingStyle = enumItem(Enum.EasingStyle, style, Enum.EasingStyle.Quad, "TweenInfo.new"),
		EasingDirection = enumItem(Enum.EasingDirection, direction, Enum.EasingDirection.Out, "TweenInfo.new"),
		RepeatCount = if repeats < 0 then math.ceil(repeats) else math.floor(repeats),
		Reverses = reverses == true,
		DelayTime = number(delayTime, 0, 6),
	}, infoMeta)
end

-- Values --------------------------------------------------------------------------------
local function trunc(x)
	return if x < 0 then math.ceil(x) else math.floor(x)
end
local function round(x)
	return math.floor(x + 0.5)
end
local function lerp(a, b, t)
	return a + (b - a) * t
end
-- A tween's write to a whole-number property rounds (semantics.json: BorderSizePixel,
-- LayoutOrder), where setting it directly truncates.
local function roundAway(x)
	return if x < 0 then -round(-x) else round(x)
end

-- An offset is a whole number of pixels: a tween rounds it, a legacy tween truncates
-- the distance it has covered (trajectories.json).
local function roundedOffset(a, b, t)
	return round(lerp(a, b, t))
end
local function truncatedOffset(a, b, t)
	return a + trunc((b - a) * t)
end

local function lerpValue(a, b, t, offset)
	local kind = typeof(a)
	if kind == "number" then
		return lerp(a, b, t)
	elseif kind == "boolean" then
		-- As a number from 0 to 1: true to false only at the end, false to true at once.
		return lerp(if a then 1 else 0, if b then 1 else 0, t) ~= 0
	elseif kind == "UDim2" then
		return UDim2.new(lerp(a.X.Scale, b.X.Scale, t), offset(a.X.Offset, b.X.Offset, t),
			lerp(a.Y.Scale, b.Y.Scale, t), offset(a.Y.Offset, b.Y.Offset, t))
	elseif kind == "UDim" then
		return UDim.new(lerp(a.Scale, b.Scale, t), offset(a.Offset, b.Offset, t))
	elseif kind == "Color3" then
		return Color3.new(lerp(a.R, b.R, t), lerp(a.G, b.G, t), lerp(a.B, b.B, t))
	elseif kind == "Vector2" then
		return Vector2.new(lerp(a.X, b.X, t), lerp(a.Y, b.Y, t))
	elseif kind == "Vector3" then
		return Vector3.new(lerp(a.X, b.X, t), lerp(a.Y, b.Y, t), lerp(a.Z, b.Z, t))
	elseif kind == "Vector2int16" then
		return roblox.Vector2int16.new(round(lerp(a.X, b.X, t)), round(lerp(a.Y, b.Y, t)))
	elseif kind == "Rect" then
		return Rect.new(lerp(a.Min.X, b.Min.X, t), lerp(a.Min.Y, b.Min.Y, t), lerp(a.Max.X, b.Max.X, t),
			lerp(a.Max.Y, b.Max.Y, t))
	elseif kind == "CFrame" then
		return a:Lerp(b, t)
	end
	return if t >= 1 then b else a
end

-- What Roblox's setters do to a value Lune would keep as given: the clamps a Back or
-- Elastic overshoot meets, and whole numbers Lune leaves fractional (legacy.json and
-- semantics.json's setters). Int32 properties (ZIndex, LayoutOrder, BorderSizePixel)
-- truncate in Lune as in Roblox.
local function clamp01(x)
	return math.clamp(x, 0, 1)
end
local TEXT = { "TextLabel", "TextButton", "TextBox" }
local SETTERS = {
	{ { "GuiObject" }, "AnchorPoint", function(v)
		return Vector2.new(clamp01(v.X), clamp01(v.Y))
	end },
	{ { "ImageLabel", "ImageButton" }, "ImageTransparency", clamp01 },
	{ { "CanvasGroup" }, "GroupTransparency", clamp01 },
	{ { "ScrollingFrame" }, "ScrollBarImageTransparency", clamp01 },
	{ { "ScrollingFrame" }, "ScrollBarThickness", function(v)
		return math.max(v, 0)
	end },
	{ { "ScrollingFrame" }, "CanvasPosition", function(v)
		return Vector2.new(math.max(v.X, 0), math.max(v.Y, 0))
	end },
	{ { "UIScale" }, "Scale", function(v)
		return math.max(v, 1e-7)
	end },
	{ TEXT, "TextSize", function(v)
		return math.clamp(trunc(v), 1, 100)
	end },
	{ TEXT, "LineHeight", function(v)
		return math.clamp(v, 0, 3)
	end },
	{ TEXT, "MaxVisibleGraphemes", function(v)
		return math.max(v, -1)
	end },
	{ { "IntValue" }, "Value", roundAway },
}
local setterCache = {}
local function setterFor(instance, property)
	local key = instance.ClassName .. "." .. property
	local found = setterCache[key]
	if found == nil then
		found = false
		for _, setter in SETTERS do
			if setter[2] == property then
				for _, className in setter[1] do
					if instance:IsA(className) then
						found = setter[3]
					end
				end
			end
		end
		setterCache[key] = found
	end
	return found or nil
end

-- Lune has no default for these until they are set, so a tween from the default reads
-- Roblox's own. Any other unreadable start is taken as the goal: no motion.
local UNSET_DEFAULTS = { ["UICorner.CornerRadius"] = UDim.new(0, 8) }

-- What TweenService:Create accepts, from Lune's reflection database: the property's
-- type, by the name Roblox's errors give it.
local TWEENABLE = { Float32 = "float", Float64 = "double", Int32 = "int", Int64 = "int64", Bool = "bool",
	CFrame = "CFrame", Rect = "Rect", Color3 = "Color3", UDim = "UDim", UDim2 = "UDim2", Vector2 = "Vector2",
	Vector2int16 = "Vector2int16", Vector3 = "Vector3" }
local LUA_TYPE = { float = "number", double = "number", int = "number", int64 = "number", bool = "boolean" }
local database = roblox.getReflectionDatabase()
local function propertyType(className, property)
	local class = database:FindClass(className)
	while class do
		local found = class.Properties[property]
		if found then
			return found.Datatype, found.Scriptability
		end
		class = class.Superclass and database:FindClass(class.Superclass)
	end
	return nil
end

-- Story time is a frame count over 60, and (j + n) / 60 - j / 60 can come out a rounding
-- error short of n / 60: a delay or cycle of n frames ends on its nth frame all the same.
local EPSILON = 1e-9

return function(hooks)
	local now, event, changed, spawn, inGame = hooks.now, hooks.event, hooks.changed, hooks.spawn, hooks.inGame

	local states = setmetatable({}, { __mode = "k" }) -- Tween instance -> its state
	local owners = setmetatable({}, { __mode = "k" }) -- instance -> property -> the state that writes it
	local legacySlots = setmetatable({}, { __mode = "k" }) -- GuiObject -> its legacy tween
	-- Playing, waiting or paused, in the order played. Roblox keeps legacy GuiObject tweens
	-- apart from Tweens (semantics.json).
	local tweenQueue, legacyQueue = {}, {}

	-- A destroyed Tween plays on in Roblox, with nothing left connected to its Completed
	-- (semantics.json); Lune refuses writes to it.
	local function setStatus(state, status)
		state.status = status
		if state.tween and not state.destroyed then
			state.destroyed = not pcall(function()
				state.tween.PlaybackState = Enum.PlaybackState[status]
			end)
		end
	end

	local function deactivate(state)
		local index = table.find(state.queue, state)
		if index then
			table.remove(state.queue, index)
		end
	end

	-- A tween that ends leaves its place to the last in its queue, as Roblox's does, so once
	-- one has ended the order tweens step and fire Completed in is no longer the play order
	-- (semantics.json).
	local function retire(state)
		local queue = state.queue
		local index = table.find(queue, state)
		if index then
			queue[index] = queue[#queue]
			queue[#queue] = nil
		end
	end

	-- While the tweens step, their signals wait until they all have, in the order they
	-- were raised, as Roblox's deferred events do: a Completed handler reads every write
	-- of that step (a tween cancelled by a takeover reads the new tween's first write).
	local announcements = nil
	local function later(fn, ...)
		if announcements then
			table.insert(announcements, table.pack(fn, ...))
		else
			fn(...)
		end
	end
	local function announce(state, status)
		if state.tween then
			if not state.destroyed then
				event(state.tween, "Completed"):Fire(Enum.PlaybackState[status])
			end
		elseif state.callback then
			spawn(state.callback, if status == "Completed" then Enum.TweenStatus.Completed else Enum.TweenStatus.Canceled)
		end
	end
	local function finish(state, status)
		if status == "Completed" then
			retire(state)
		else
			deactivate(state)
		end
		setStatus(state, status)
		later(announce, state, status)
	end

	-- Writes the curve at alpha, or with `ending` the goal (alpha 1) or the start (0)
	-- exactly.
	local function write(state, alpha, ending)
		local instance = state.instance
		local claims = owners[instance]
		for _, goal in state.goals do
			local property = goal.property
			if claims[property] ~= state then
				continue
			end
			local start = state.start[property]
			local value
			if ending then
				value = if alpha == 1 then goal.value else start
			else
				value = lerpValue(start, goal.value, alpha, state.offset)
				if goal.integer then
					value = roundAway(value)
				end
			end
			local setter = setterFor(instance, property)
			if setter then
				value = setter(value)
			end
			local okRead, before = pcall(function()
				return instance[property]
			end)
			local okWrite = pcall(function()
				instance[property] = value
			end)
			if okWrite and changed and (not okRead or before ~= instance[property]) then
				later(changed, instance, property)
			end
		end
	end

	-- A tween with no goals plays out its time all the same (semantics.json: EMP).
	local function owns(state)
		if #state.goals == 0 then
			return true
		end
		local claims = owners[state.instance]
		for _, goal in state.goals do
			if claims[goal.property] == state then
				return true
			end
		end
		return false
	end

	local function claim(state)
		local claims = owners[state.instance]
		if not claims then
			claims = {}
			owners[state.instance] = claims
		end
		for _, goal in state.goals do
			claims[goal.property] = state
		end
		deactivate(state)
		table.insert(state.queue, state)
	end

	local function begin(state, firstPlay)
		state.start = {}
		for _, goal in state.goals do
			local okRead, value = pcall(function()
				return state.instance[goal.property]
			end)
			state.start[goal.property] = if okRead
				then value
				else UNSET_DEFAULTS[state.instance.ClassName .. "." .. goal.property] or goal.value
		end
		state.count = 0
		state.phaseStart = now()
		state.waiting = state.delay > 0
		-- A replay waits out its delay reading Playing; only the first play reads Delayed.
		setStatus(state, if state.waiting and firstPlay then "Delayed" else "Playing")
		claim(state)
	end

	-- One step of a playing tween. A delay that has passed starts the curve on this step
	-- and writes nothing; a cycle that has passed writes its end (the start when it
	-- reverses) and starts the next repeat on this step, so what ran over is dropped.
	local function step(state, t)
		local elapsed = t - state.phaseStart
		if state.waiting then
			if elapsed + EPSILON >= state.delay then
				state.waiting = false
				state.phaseStart = t
				setStatus(state, "Playing")
			end
			return
		end
		local cycle = state.time * (if state.reverses then 2 else 1)
		if elapsed + EPSILON >= cycle then
			write(state, if state.reverses then 0 else 1, true)
			if state.repeats < 0 or state.count < state.repeats then
				state.count += 1
				state.phaseStart = t
				state.waiting = state.delay > 0
				if state.waiting then
					setStatus(state, "Delayed")
				end
			else
				finish(state, "Completed")
			end
			return
		end
		local x = elapsed / state.time
		if x > 1 then
			x = 2 - x
		end
		write(state, state.ease(x))
	end

	-- A tween that a newer one took every property from is cancelled on the next step,
	-- the first played first, before any tween moves. Then they move from the end of each
	-- queue, which is the order Roblox fires their Completed in; one that ends takes the
	-- last in the queue, already stepped, into its place.
	local function stepAll()
		local t = now()
		announcements = {}
		for _, queue in { tweenQueue, legacyQueue } do
			for _, state in table.clone(queue) do
				if not owns(state) then
					finish(state, "Cancelled")
				end
			end
		end
		for _, queue in { tweenQueue, legacyQueue } do
			for index = #queue, 1, -1 do
				local state = queue[index]
				if state.status == "Playing" or state.status == "Delayed" then
					step(state, t)
				end
			end
		end
		local due = announcements
		announcements = nil
		for _, entry in due do
			entry[1](table.unpack(entry, 2, entry.n))
		end
	end

	-- TweenService ------------------------------------------------------------------------
	roblox.implementMethod("TweenService", "GetValue", function(_, alpha, style, direction)
		if type(alpha) ~= "number" then
			error(`invalid argument #1 to 'GetValue' (number expected, got {typeof(alpha)})`, 0)
		end
		local styleItem = enumItem(Enum.EasingStyle, style, nil, "TweenService:GetValue")
		local directionItem = enumItem(Enum.EasingDirection, direction, nil, "TweenService:GetValue")
		if styleItem == nil or directionItem == nil then
			error("TweenService:GetValue needs an EasingStyle and an EasingDirection", 0)
		end
		return ease(STYLES[styleItem.Name], directionItem.Name, math.clamp(alpha, 0, 1))
	end)

	roblox.implementMethod("TweenService", "Create", function(_, instance, info, goals)
		if typeof(instance) ~= "Instance" then
			error("TweenService:Create failed because Instance is null", 0)
		end
		if getmetatable(info :: any) ~= infoMeta then
			error(`invalid argument #2 to 'Create' (TweenInfo expected, got {typeof(info)})`, 0)
		end
		if type(goals) ~= "table" then
			error(`invalid argument #3 to 'Create' (table expected, got {typeof(goals)})`, 0)
		end
		local list = {}
		for property, value in goals do
			local datatype, scriptability = propertyType(instance.ClassName, property)
			if datatype == nil then
				error(`TweenService:Create no property named '{property}' for object '{instance.Name}'`, 0)
			end
			local typeName = TWEENABLE[datatype]
			if typeName == nil or scriptability == "Read" or scriptability == "None" then
				error(`TweenService:Create property named '{property}' on object '{instance.Name}' is not a data type `
					.. `that can be tweened`, 0)
			end
			if typeof(value) ~= (LUA_TYPE[typeName] or typeName) then
				error(`TweenService:Create property named '{property}' cannot be tweened due to type mismatch `
					.. `(property is a '{typeName}', but given type is '{typeof(value)}')`, 0)
			end
			-- GuiObject.Transparency is BackgroundTransparency by another name, which Lune
			-- cannot read.
			local written = if property == "Transparency" and instance:IsA("GuiObject")
				then "BackgroundTransparency"
				else property
			-- A whole-number goal is kept as setting it would leave it: an int drops its
			-- fraction (semantics.json: INT2), and an int64 rounds, as IntValue.Value's
			-- setter does (a tween to a fractional int64 is not measured).
			local integer = typeName == "int" or typeName == "int64"
			if typeName == "int" then
				value = trunc(value)
			elseif typeName == "int64" then
				value = roundAway(value)
			end
			table.insert(list, { property = written, value = value, integer = integer })
		end
		table.sort(list, function(a, b)
			return a.property < b.property
		end)

		local tween = roblox.Instance.new("Tween")
		tween.Instance = instance
		local style, direction = info.EasingStyle.Name, info.EasingDirection.Name
		local state = {
			tween = tween,
			info = info,
			instance = instance,
			goals = list,
			time = info.Time,
			delay = info.DelayTime,
			repeats = info.RepeatCount,
			reverses = info.Reverses,
			ease = function(x)
				return ease(STYLES[style], direction, x)
			end,
			offset = roundedOffset,
			queue = tweenQueue,
		}
		states[tween] = state
		setStatus(state, "Begin")
		return tween
	end)

	pcall(roblox.implementProperty, "Tween", "TweenInfo", function(tween)
		local state = states[tween]
		return state and state.info
	end)
	pcall(roblox.implementProperty, "TweenBase", "Completed", function(tween)
		return event(tween, "Completed")
	end)

	roblox.implementMethod("TweenBase", "Play", function(tween)
		local state = states[tween]
		if state == nil or state.status == "Playing" or state.status == "Delayed" then
			return
		end
		if state.status == "Paused" then
			state.phaseStart = now() - state.pausedFor
			setStatus(state, "Playing")
			claim(state)
		else
			begin(state, state.status == "Begin")
		end
	end)
	-- Pause holds a tween that reads Playing; one waiting out its first delay goes on. A
	-- paused tween stays in its queue, so a newer tween taking its properties cancels it.
	roblox.implementMethod("TweenBase", "Pause", function(tween)
		local state = states[tween]
		if state and state.status == "Playing" then
			state.pausedFor = now() - state.phaseStart
			setStatus(state, "Paused")
		end
	end)
	-- Cancel after Completed fires Completed again, with Cancelled (semantics.json).
	local CANCELS = { Playing = true, Delayed = true, Paused = true, Completed = true }
	roblox.implementMethod("TweenBase", "Cancel", function(tween)
		local state = states[tween]
		if state and CANCELS[state.status] then
			finish(state, "Cancelled")
		end
	end)

	-- Legacy GuiObject tweens -------------------------------------------------------------
	-- One at a time on an element: another is refused unless it overrides, which cancels
	-- the first and runs its callback at once with Canceled. Only an element in the data
	-- model tweens, and bad arguments leave the first playing (semantics.json).
	local function legacy(instance, goals, direction, style, time, override, callback)
		if inGame and not inGame(instance) then
			error("Can only tween objects in the workspace", 0)
		end
		local styleName = castEnum(Enum.EasingStyle, style, Enum.EasingStyle.Quad, "EasingStyle").Name
		local directionName = castEnum(Enum.EasingDirection, direction, Enum.EasingDirection.Out, "EasingDirection").Name
		local current = legacySlots[instance]
		if current and current.status == "Playing" then
			if not override then
				return false
			end
			finish(current, "Cancelled")
		end
		local state = {
			instance = instance,
			goals = goals,
			time = if time == nil then 1 else time,
			delay = 0,
			repeats = 0,
			reverses = false,
			ease = function(x)
				return legacyEase(styleName, directionName, x)
			end,
			offset = truncatedOffset,
			callback = if type(callback) == "function" then callback else nil,
			queue = legacyQueue,
		}
		legacySlots[instance] = state
		begin(state, true)
		return true
	end
	local function udim2(value, what)
		if typeof(value) ~= "UDim2" then
			error(`{what} expects a UDim2, got {typeof(value)}`, 0)
		end
		return value
	end
	roblox.implementMethod("GuiObject", "TweenPosition", function(instance, position, direction, style, time, override, callback)
		local goals = { { property = "Position", value = udim2(position, "GuiObject:TweenPosition") } }
		return legacy(instance, goals, direction, style, time, override, callback)
	end)
	roblox.implementMethod("GuiObject", "TweenSize", function(instance, size, direction, style, time, override, callback)
		local goals = { { property = "Size", value = udim2(size, "GuiObject:TweenSize") } }
		return legacy(instance, goals, direction, style, time, override, callback)
	end)
	roblox.implementMethod("GuiObject", "TweenSizeAndPosition",
		function(instance, size, position, direction, style, time, override, callback)
			local goals = { { property = "Position", value = udim2(position, "GuiObject:TweenSizeAndPosition") },
				{ property = "Size", value = udim2(size, "GuiObject:TweenSizeAndPosition") } }
			return legacy(instance, goals, direction, style, time, override, callback)
		end)

	local function moving()
		local list = {}
		for _, queue in { tweenQueue, legacyQueue } do
			for _, state in queue do
				if state.status == "Paused" then
					continue
				end
				local properties = {}
				for _, goal in state.goals do
					if owners[state.instance][goal.property] == state then
						table.insert(properties, goal.property)
					end
				end
				table.insert(list, { instance = state.instance, properties = properties, forever = state.repeats < 0 })
			end
		end
		return list
	end

	return { TweenInfo = TweenInfo, step = stepAll, moving = moving }
end
