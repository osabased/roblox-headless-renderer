-- TweenService:GetValue as Roblox computes it, for tests/fixtures/tween/getvalue.json.
--
-- Run it in Studio (edit mode is enough), through the Studio MCP's execute_luau or
-- the command bar with `print` around the result. It returns JSON: every style
-- GetValue accepts (Bezier and Spring raise an error there), each direction, at
-- alphas 0, 0.01 .. 1 and at a few outside 0..1. Values are written with %.17g, so
-- the fixture keeps what Studio returned to the last bit.

local HttpService = game:GetService("HttpService")
local TweenService = game:GetService("TweenService")

local styles = { "Linear", "Sine", "Back", "Quad", "Quart", "Quint", "Bounce", "Elastic", "Exponential", "Circular", "Cubic" }
local directions = { "In", "Out", "InOut" }
local alphas = {}
for i = 0, 100 do
	alphas[#alphas + 1] = i / 100
end
local extra = { -0.5, -0.01, 1.01, 1.5, 2 }

local out = { studioVersion = version(), alphas = alphas, extraAlphas = extra, values = {}, extra = {} }
for _, style in styles do
	out.values[style] = {}
	out.extra[style] = {}
	for _, direction in directions do
		local function row(list)
			local values = {}
			for _, alpha in list do
				local value = TweenService:GetValue(alpha, Enum.EasingStyle[style], Enum.EasingDirection[direction])
				values[#values + 1] = string.format("%.17g", value)
			end
			return values
		end
		out.values[style][direction] = row(alphas)
		out.extra[style][direction] = row(extra)
	end
end
return HttpService:JSONEncode(out)
