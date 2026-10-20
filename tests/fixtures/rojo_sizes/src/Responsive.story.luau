--!strict
-- Responsive patterns that arrange UI from sizes, reported as "name = value" rows.
-- Plain Roblox API, so the same function runs in Studio for the reference numbers.
local RunService = game:GetService("RunService")

local function fmt(v: Vector2): string
	return string.format("%g,%g", math.round(v.X * 10) / 10, math.round(v.Y * 10) / 10)
end

return function(target: Frame)
	local made: { Instance } = {}
	local function new(className: string, props: { [string]: any }): any
		local instance = Instance.new(className)
		for key, value in props do
			if key ~= "Parent" then
				(instance :: any)[key] = value
			end
		end
		instance.Parent = props.Parent
		table.insert(made, instance)
		return instance
	end

	local stage = new("Frame", { Name = "Stage", Size = UDim2.fromScale(0.6, 1), BackgroundTransparency = 1, Parent = target })

	-- A: a list's canvas from its AbsoluteContentSize.
	local list = new("ScrollingFrame", {
		Name = "List", Size = UDim2.fromOffset(300, 200), CanvasSize = UDim2.new(), AutomaticCanvasSize = Enum.AutomaticSize.None, Parent = stage,
	})
	local listLayout = new("UIListLayout", { Padding = UDim.new(0, 8), SortOrder = Enum.SortOrder.LayoutOrder, Parent = list })
	for i = 1, 6 do
		new("Frame", { Name = "Row" .. i, LayoutOrder = i, Size = UDim2.new(1, 0, 0, 40), Parent = list })
	end
	listLayout:GetPropertyChangedSignal("AbsoluteContentSize"):Connect(function()
		list.CanvasSize = UDim2.fromOffset(0, listLayout.AbsoluteContentSize.Y)
	end)

	-- B: a pill as wide as its text.
	local pill = new("TextLabel", {
		Name = "Pill", Position = UDim2.fromOffset(320, 0), Size = UDim2.fromOffset(0, 32), TextSize = 18,
		FontFace = Font.new("rbxasset://fonts/families/FredokaOne.json"), Text = "Hello, responsive world", Parent = stage,
	})
	pill:GetPropertyChangedSignal("TextBounds"):Connect(function()
		pill.Size = UDim2.fromOffset(pill.TextBounds.X + 24, 32)
	end)

	-- C: a popover placed at the pill's right edge (depends on B's result).
	local badge = new("Frame", { Name = "Badge", Size = UDim2.fromOffset(20, 20), Parent = target })
	local function place()
		local origin = target.AbsolutePosition
		badge.Position = UDim2.fromOffset(pill.AbsolutePosition.X - origin.X + pill.AbsoluteSize.X, pill.AbsolutePosition.Y - origin.Y)
	end
	pill:GetPropertyChangedSignal("AbsoluteSize"):Connect(place)
	pill:GetPropertyChangedSignal("AbsolutePosition"):Connect(place)

	-- D: three grid columns from the container's width.
	local grid = new("Frame", { Name = "Grid", Position = UDim2.fromOffset(0, 220), Size = UDim2.new(1, 0, 0, 200), Parent = stage })
	local gridLayout = new("UIGridLayout", { CellPadding = UDim2.fromOffset(10, 10), Parent = grid })
	for i = 1, 5 do
		new("Frame", { Name = "Cell" .. i, Parent = grid })
	end
	grid:GetPropertyChangedSignal("AbsoluteSize"):Connect(function()
		local w = (grid.AbsoluteSize.X - 20) / 3
		gridLayout.CellSize = UDim2.fromOffset(w, w * 0.5)
	end)

	-- E: a breakpoint from a container's width.
	local mode = "unset"
	local bar = new("Frame", { Name = "Bar", Position = UDim2.fromOffset(0, 440), Size = UDim2.new(1, 0, 0, 30), Parent = stage })
	bar:GetPropertyChangedSignal("AbsoluteSize"):Connect(function()
		mode = if bar.AbsoluteSize.X >= 900 then "wide" else "narrow"
	end)

	-- F: a read in task.defer only, no signal.
	local deferred = "pending"
	task.defer(function()
		deferred = fmt(stage.AbsoluteSize)
	end)

	-- G: a read right after mount, synchronous.
	local sync = fmt(stage.AbsoluteSize)

	local report = new("Frame", { Name = "Report", Position = UDim2.fromScale(0.6, 0), Size = UDim2.fromScale(0.4, 1), Parent = target })
	new("UIListLayout", { SortOrder = Enum.SortOrder.LayoutOrder, Parent = report })
	local rows: { [string]: TextLabel } = {}
	local order = 0
	local function row(name: string, value: string)
		local label = rows[name]
		if not label then
			order += 1
			label = new("TextLabel", {
				Name = name, LayoutOrder = order, Size = UDim2.new(1, 0, 0, 20), TextSize = 14,
				TextXAlignment = Enum.TextXAlignment.Left, Parent = report,
			})
			rows[name] = label
		end
		label.Text = name .. " = " .. value
	end
	local function refresh()
		row("AListCanvas", tostring(list.CanvasSize.Y.Offset))
		row("AContentSize", fmt(listLayout.AbsoluteContentSize))
		row("BPillTextBounds", fmt(pill.TextBounds))
		row("BPillSize", fmt(pill.AbsoluteSize))
		row("CBadgePosition", string.format("%g,%g", badge.Position.X.Offset, badge.Position.Y.Offset))
		row("DCellSize", string.format("%g,%g", math.round(gridLayout.CellSize.X.Offset * 10) / 10, math.round(gridLayout.CellSize.Y.Offset * 10) / 10))
		row("DCell5Position", fmt((grid:FindFirstChild("Cell5") :: Frame).AbsolutePosition))
		row("EMode", mode)
		row("FDeferred", deferred)
		row("GSync", sync)
		row("TargetSize", fmt(target.AbsoluteSize))
		row("TargetPosition", fmt(target.AbsolutePosition))
	end
	refresh()
	local connection = RunService.Heartbeat:Connect(refresh)
	return function()
		connection:Disconnect()
		for i = #made, 1, -1 do
			made[i]:Destroy()
		end
	end
end
