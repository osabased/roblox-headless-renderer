-- An installed package's entry: it reaches its own files with @self/.
local style = require("@self/style")

return function(text: string)
	local tag = Instance.new("TextLabel")
	tag.Name = "Tag"
	tag.Text = text
	tag.Size = style.size
	tag.BackgroundColor3 = style.background
	return tag
end
