-- What a story reads of the player's device and settings, one label per read (its
-- value, or the error), plus TextService:GetTextBoundsAsync, GuiService:Select and the
-- InputSink a new object starts with.
local GuiService = game:GetService("GuiService")
local TextService = game:GetService("TextService")
local UserInputService = game:GetService("UserInputService")

local function bounds(text, size, width)
	local params = Instance.new("GetTextBoundsParams")
	params.Text = text
	params.Size = size
	params.Font = Font.fromEnum(Enum.Font.BuilderSans)
	params.Width = width
	local measured = TextService:GetTextBoundsAsync(params)
	return `{measured.X},{measured.Y}`
end

local function button(name, order, parent)
	local object = Instance.new("TextButton")
	object.Name = name
	object.SelectionOrder = order
	object.Parent = parent
	return object
end

local function selected(container, target)
	container.Parent = target
	GuiService:Select(container)
	local object = GuiService.SelectedObject
	return if object then object.Name else "nil"
end

local reads = {
	PreferredInput = function()
		return UserInputService.PreferredInput.Name
	end,
	LastInputType = function()
		return UserInputService:GetLastInputType().Name
	end,
	TouchEnabled = function()
		return tostring(UserInputService.TouchEnabled)
	end,
	KeyboardEnabled = function()
		return tostring(UserInputService.KeyboardEnabled)
	end,
	MouseEnabled = function()
		return tostring(UserInputService.MouseEnabled)
	end,
	GamepadEnabled = function()
		return tostring(UserInputService.GamepadEnabled)
	end,
	ViewportDisplaySize = function()
		return GuiService.ViewportDisplaySize.Name
	end,
	PreferredTextSize = function()
		return GuiService.PreferredTextSize.Name
	end,
	PreferredTransparency = function()
		return tostring(GuiService.PreferredTransparency)
	end,
	ReducedMotionEnabled = function()
		return tostring(GuiService.ReducedMotionEnabled)
	end,
	TopbarInset = function()
		local inset = GuiService.TopbarInset
		return `{inset.Min.X},{inset.Min.Y},{inset.Max.X},{inset.Max.Y}`
	end,
	BoundsLine = function()
		return bounds("Hello there", 20, 0)
	end,
	BoundsWrapped = function()
		return bounds("Hello there", 20, 50)
	end,
	BoundsLines = function()
		return bounds("Hi\nthere", 10, 0)
	end,
	Select = function(target)
		local container = Instance.new("Frame")
		local hidden = button("Hidden", -5, container)
		hidden.Visible = false
		local folded = Instance.new("Frame")
		folded.Visible = false
		folded.Parent = container
		button("Folded", -3, folded)
		local plain = Instance.new("Frame")
		plain.SelectionOrder = -1
		plain.Parent = container
		button("Second", 2, container)
		button("First", 1, container)
		return selected(container, target)
	end,
	SelectNothing = function(target)
		local container = Instance.new("Frame")
		button("Kept", 1, container)
		selected(container, target)
		return selected(Instance.new("Frame"), target)
	end,
	InputSink = function()
		local sinks = {}
		for _, class in { "TextButton", "ImageButton", "TextBox", "Frame", "TextLabel" } do
			table.insert(sinks, `{class}={Instance.new(class).InputSink.Name}`)
		end
		return table.concat(sinks, " ")
	end,
}

return function(target)
	for name, read in reads do
		local ok, value = pcall(read, target)
		local label = Instance.new("TextLabel")
		label.Name = name
		label.Size = UDim2.fromOffset(400, 20)
		label.Text = if ok then value else `error: {value}`
		label.Parent = target
	end
end
