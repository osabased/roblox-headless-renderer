--!strict
local RunService = game:GetService("RunService")

local Vide = require(script.Parent.Parent.Packages.vide)

local create = Vide.create
local source = Vide.source

local function probe(read: () -> unknown): string
	local ok, value = pcall(read)
	if not ok then
		return "error: " .. tostring(value)
	end
	return tostring(value)
end

local function row(name: string, text: () -> string, order: number)
	return create("TextLabel")({
		Name = name,
		LayoutOrder = order,
		Size = UDim2.new(1, 0, 0, 0),
		AutomaticSize = Enum.AutomaticSize.Y,
		BackgroundTransparency = 1,
		TextXAlignment = Enum.TextXAlignment.Left,
		TextSize = 14,
		TextColor3 = Color3.new(1, 1, 1),
		Text = function()
			return name .. " = " .. text()
		end,
	})
end

return {
	vide = Vide,
	story = function(props: { target: Frame })
		local target = props.target
		local half = create("Frame")({
			Name = "Half",
			Size = UDim2.fromScale(0.5, 0.5),
			BackgroundTransparency = 1,
		})
		local beforeParent = probe(function()
			return half.AbsoluteSize
		end)
		half.Parent = target
		local atMount = probe(function()
			return half.AbsoluteSize
		end)
		local positionAtMount = probe(function()
			return half.AbsolutePosition
		end)
		local deferred = source("pending")
		local heartbeat = source("pending")
		local changed = source("never fired")
		task.defer(function()
			deferred(probe(function()
				return half.AbsoluteSize
			end))
		end)
		local ok, err = pcall(function()
			RunService.Heartbeat:Once(function()
				heartbeat(probe(function()
					return half.AbsoluteSize
				end))
			end)
			half:GetPropertyChangedSignal("AbsoluteSize"):Connect(function()
				changed(probe(function()
					return half.AbsoluteSize
				end))
			end)
		end)
		if not ok then
			heartbeat("error: " .. tostring(err))
		end

		local function fixed(value: string): () -> string
			return function()
				return value
			end
		end

		return create("Frame")({
			Name = "Sizes",
			Size = UDim2.fromScale(1, 1),
			BackgroundColor3 = Color3.new(0, 0, 0),
			create("UIListLayout")({ SortOrder = Enum.SortOrder.LayoutOrder }),
			row("HalfBeforeParent", fixed(beforeParent), 1),
			row("HalfAtMount", fixed(atMount), 2),
			row("HalfPositionAtMount", fixed(positionAtMount), 3),
			row("HalfDeferred", deferred, 4),
			row("HalfHeartbeat", heartbeat, 5),
			row("HalfChanged", changed, 6),
		})
	end,
}
