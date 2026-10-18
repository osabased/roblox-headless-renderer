-- A legacy Font then a FontFace, the order UI libraries with defaults set them, and a
-- legacy Font alone.
return function(target)
	local face = Instance.new("TextLabel")
	face.Name = "Face"
	face.Font = Enum.Font.SourceSans
	face.FontFace = Font.new("rbxasset://fonts/families/BuilderSans.json", Enum.FontWeight.Bold)
	face.Parent = target
	local legacy = Instance.new("TextLabel")
	legacy.Name = "Legacy"
	legacy.Font = Enum.Font.GothamBold
	legacy.Parent = target
	return function()
		face:Destroy()
		legacy:Destroy()
	end
end
