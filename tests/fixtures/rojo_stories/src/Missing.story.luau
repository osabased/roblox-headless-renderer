-- A string require that leads nowhere.
local NotThere = require("./NotThere")

return function(target)
	NotThere(target)
end
