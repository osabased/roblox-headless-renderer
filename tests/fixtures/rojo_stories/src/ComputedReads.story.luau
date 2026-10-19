--!strict
-- What Roblox works out as it lays GUI out, read while the story runs: one label per
-- read, named Subject.Property, with the value or the error. A class name is a new
-- element of that class; Template is a TextLabel from the project's files and Clone a
-- copy of it.
local template = script.Parent:FindFirstChild("ComputedTemplate") :: TextLabel

local READS: { { string } } = {
	{ "Frame", "AbsoluteSize", "AbsolutePosition", "AbsoluteRotation", "GuiState" },
	{ "TextLabel", "TextBounds", "TextFits", "OpenTypeFeaturesError" },
	{ "TextButton", "TextBounds", "TextFits", "OpenTypeFeaturesError", "GuiState" },
	{ "TextBox", "TextBounds", "TextFits", "OpenTypeFeaturesError", "CursorPosition", "SelectionStart" },
	{ "ImageLabel", "IsLoaded" },
	{ "ImageButton", "IsLoaded", "GuiState" },
	{ "VideoFrame", "IsLoaded", "Resolution", "TimeLength" },
	{ "ScrollingFrame", "AbsoluteCanvasSize", "AbsoluteWindowSize", "AbsoluteSize" },
	{ "CanvasGroup", "AbsoluteSize", "GuiState" },
	{ "ViewportFrame", "AbsolutePosition" },
	{ "ScreenGui", "AbsoluteSize", "AbsolutePosition", "AbsoluteRotation" },
	{ "BillboardGui", "CurrentDistance", "DistanceStep", "AbsoluteSize" },
	{ "SurfaceGui", "AbsoluteSize" },
	{ "UIListLayout", "AbsoluteContentSize" },
	{ "UIGridLayout", "AbsoluteContentSize", "AbsoluteCellCount", "AbsoluteCellSize" },
	{ "UIPageLayout", "AbsoluteContentSize" },
	{ "UITableLayout", "AbsoluteContentSize" },
	{ "Target", "AbsoluteSize", "AbsolutePosition", "AbsoluteRotation", "GuiState" },
	{ "Screen", "AbsoluteSize", "AbsolutePosition" },
	{ "Template", "AbsoluteSize", "GuiState", "TextBounds", "TextFits" },
	{ "Clone", "TextBounds", "TextFits" },
}

local function show(value: any): string
	if typeof(value) == "Vector2" then
		return `{value.X},{value.Y}`
	elseif typeof(value) == "EnumItem" then
		return value.Name
	elseif typeof(value) == "string" then
		return `"{value}"`
	end
	return tostring(value)
end

return function(target: Frame)
	local given: { [string]: any } = {
		Target = target,
		Screen = target.Parent,
		Template = template,
		Clone = template:Clone(),
	}
	for _, read in READS do
		local subject = given[read[1]] or Instance.new(read[1] :: any)
		for index = 2, #read do
			local property = read[index]
			local ok, value = pcall(function()
				return subject[property]
			end)
			local label = Instance.new("TextLabel")
			label.Name = `{read[1]}.{property}`
			label.Size = UDim2.fromOffset(400, 20)
			label.Text = if ok then show(value) else `error: {string.split(tostring(value), "\n")[1]}`
			label.Parent = target
		end
	end
end
