-- String requires (Roblox's require-by-string), through a package link.
local Tag = require("../Packages/Tag")

return function(target)
	local tag = Tag("New")
	tag.Position = UDim2.fromOffset(10, 20)
	tag.Parent = target
	return function()
		tag:Destroy()
	end
end
