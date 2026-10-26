-- Legacy GuiObject tweens (TweenPosition) as Roblox plays them, for
-- tests/fixtures/tween/legacy.json.
--
-- Run it in Studio Play mode through the Studio MCP's execute_luau; it returns JSON.
-- The Server datamodel is the one to use: a client's tweens step only while its
-- viewport renders, so an unattended Studio's client never finishes. Each style and
-- direction tweens a frame's Position from 0 to UDim2.new(1, 0, 0, 0) over DURATION
-- seconds, so X.Scale is the legacy easing's alpha itself. Samples are taken every
-- Heartbeat against a clock probe, as in record_tween_trajectories.luau.
--
-- `setters` is what properties a tween can push past their range (a Back or Elastic
-- overshoot) read after such a value is set: some clamp it, most keep it.

local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")

local DURATION = 1
local RECORD_S = 1.15

local gui = Instance.new("ScreenGui")
gui.Name = "RHRTweenLegacyRecording"
gui.Parent = if Players.LocalPlayer then Players.LocalPlayer:WaitForChild("PlayerGui") else ReplicatedStorage

local probe = Instance.new("NumberValue")
probe.Parent = gui
local probeTween = TweenService:Create(probe, TweenInfo.new(100, Enum.EasingStyle.Linear), { Value = 100 })

local function encode(value)
	local kind = typeof(value)
	if kind == "Vector2" then
		return { value.X, value.Y }
	elseif kind == "UDim" then
		return { value.Scale, value.Offset }
	elseif kind == "Color3" then
		return { value.R, value.G, value.B }
	end
	return value
end
local setters = {}
for _, case in {
	{ "Frame", "AnchorPoint", Vector2.new(1.5, -0.5) },
	{ "Frame", "AnchorPoint", Vector2.new(-0.2, 1.0999) },
	{ "Frame", "BackgroundTransparency", 1.5 },
	{ "Frame", "BackgroundTransparency", -0.5 },
	{ "Frame", "BackgroundColor3", Color3.new(1.5, -0.5, 0.5) },
	{ "Frame", "Rotation", 400 },
	{ "ImageLabel", "ImageTransparency", 1.5 },
	{ "ImageLabel", "ImageTransparency", -0.5 },
	{ "ImageButton", "ImageTransparency", 1.5 },
	{ "TextLabel", "TextTransparency", -0.2 },
	{ "TextLabel", "TextStrokeTransparency", 1.3 },
	{ "TextLabel", "TextSize", 150 },
	{ "TextLabel", "TextSize", 0.5 },
	{ "TextLabel", "LineHeight", 5 },
	{ "TextLabel", "LineHeight", 0.5 },
	{ "CanvasGroup", "GroupTransparency", 1.5 },
	{ "CanvasGroup", "GroupTransparency", -0.5 },
	{ "ScrollingFrame", "ScrollBarImageTransparency", 1.5 },
	{ "ScrollingFrame", "ScrollBarImageTransparency", -0.5 },
	{ "ScrollingFrame", "ScrollBarThickness", -3 },
	{ "UICorner", "CornerRadius", UDim.new(-0.5, -10) },
	{ "UIStroke", "Transparency", 1.4 },
	{ "UIStroke", "Thickness", -2 },
	{ "UIScale", "Scale", -1 },
	{ "UIGradient", "Offset", Vector2.new(3, -3) },
	{ "UIPadding", "PaddingLeft", UDim.new(0, -5) },
} do
	local instance = Instance.new(case[1])
	instance[case[2]] = case[3]
	setters[#setters + 1] = { class = case[1], property = case[2], set = encode(case[3]), read = encode(instance[case[2]]) }
	instance:Destroy()
end

local styles = { "Linear", "Sine", "Back", "Quad", "Quart", "Quint", "Bounce", "Elastic", "Exponential", "Circular", "Cubic" }
local directions = { "In", "Out", "InOut" }
local curves, frames, errors = {}, {}, {}
for _, style in styles do
	for _, direction in directions do
		local key = style .. "." .. direction
		local frame = Instance.new("Frame")
		frame.Parent = gui
		frames[key] = frame
		curves[key] = {}
	end
end
for key, frame in frames do
	local style, direction = string.match(key, "^(%w+)%.(%w+)$")
	local ok, result = pcall(function()
		return frame:TweenPosition(UDim2.new(1, 0, 0, 0), Enum.EasingDirection[direction], Enum.EasingStyle[style], DURATION)
	end)
	if not ok or result ~= true then
		errors[key] = tostring(result)
	end
end
probeTween:Play()

local done = false
local connection = RunService.Heartbeat:Connect(function()
	local e = probe.Value
	for key, frame in frames do
		local list = curves[key]
		list[#list + 1] = { e, frame.Position.X.Scale }
	end
	if e >= RECORD_S then
		done = true
	end
end)
while not done do
	task.wait()
end
connection:Disconnect()
gui:Destroy()

for _, list in curves do
	for i, sample in list do
		list[i] = string.format("%.9g %.9g", sample[1], sample[2])
	end
end
return HttpService:JSONEncode({
	studioVersion = version(),
	duration = DURATION,
	curves = curves,
	errors = errors,
	setters = setters,
})
