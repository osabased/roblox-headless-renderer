-- A child with a lower ZIndex than its parent: on top of it under Sibling, as UI Labs
-- mounts stories, and hidden behind it under Global.
return function(target)
	local card = Instance.new("Frame")
	card.Name = "Card"
	card.ZIndex = 2
	card.Position = UDim2.fromOffset(100, 100)
	card.Size = UDim2.fromOffset(200, 100)
	card.BackgroundColor3 = Color3.fromRGB(0, 0, 255)
	card.BorderSizePixel = 0
	card.Parent = target
	local badge = Instance.new("Frame")
	badge.Name = "Badge"
	badge.Size = UDim2.fromScale(1, 1)
	badge.BackgroundColor3 = Color3.fromRGB(255, 0, 0)
	badge.BorderSizePixel = 0
	badge.Parent = card
	return function()
		card:Destroy()
	end
end
