-- Roblox's profiler and memory-category calls, which UI libraries make every frame.
local RunService = game:GetService("RunService")

return function(target)
	debug.setmemorycategory("Profiled")
	local bar = Instance.new("Frame")
	bar.Name = "Bar"
	bar.Size = UDim2.fromOffset(10, 10)
	bar.Parent = target
	debug.resetmemorycategory()
	local connection = RunService.Heartbeat:Connect(function()
		debug.profilebegin("grow")
		bar.Size = UDim2.fromOffset(100, 10)
		debug.profileend()
	end)
	return function()
		connection:Disconnect()
		bar:Destroy()
	end
end
