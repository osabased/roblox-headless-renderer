--!strict
-- Motion that a timer starts on Heartbeat, with no tween: the capture waits for the
-- timer, then stops at the cap and names what moves.
local RunService = game:GetService("RunService")

return function(target: Frame)
	local drifter = Instance.new("Frame")
	drifter.Name = "Drifter"
	drifter.Size = UDim2.fromOffset(40, 40)
	drifter.Parent = target
	task.delay(1, function()
		RunService.Heartbeat:Connect(function()
			drifter.Position += UDim2.fromOffset(1, 0)
		end)
	end)
end
