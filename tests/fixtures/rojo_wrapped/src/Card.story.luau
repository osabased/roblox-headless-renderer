-- A story in a project whose default.project.json only wraps another.
return function(target)
	local card = Instance.new("Frame")
	card.Name = "Card"
	card.Position = UDim2.fromOffset(40, 40)
	card.Size = UDim2.fromOffset(160, 90)
	card.Parent = target
	return function()
		card:Destroy()
	end
end
