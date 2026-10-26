--!strict
-- A spinner that turns forever: the capture stops at the cap and names it.
local TweenService = game:GetService("TweenService")

return function(target: Frame)
	local spinner = Instance.new("Frame")
	spinner.Name = "Spinner"
	spinner.Size = UDim2.fromOffset(40, 40)
	spinner.Parent = target
	TweenService:Create(spinner, TweenInfo.new(1, Enum.EasingStyle.Linear, Enum.EasingDirection.In, -1),
		{ Rotation = 360 }):Play()
end
