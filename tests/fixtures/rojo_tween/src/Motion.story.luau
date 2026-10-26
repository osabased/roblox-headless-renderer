--!strict
-- Tweens played at mount: where they are at 0.5 s of story time, and where they settle.
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")

local function frame(name: string, position: UDim2, parent: Instance): Frame
	local instance = Instance.new("Frame")
	instance.Name = name
	instance.Position = position
	instance.Size = UDim2.fromOffset(40, 40)
	instance.Parent = parent
	return instance
end

return function(target: Frame)
	-- Quad Out over 1 s: 75% of the way at 0.5 s.
	local slide = frame("Slide", UDim2.new(), target)
	local slideTween = TweenService:Create(slide, TweenInfo.new(1, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
		{ Position = UDim2.fromOffset(400, 0) })
	slideTween:Play()

	-- Linear over 0.5 s after a 0.25 s delay: halfway at 0.5 s.
	local fade = frame("Fade", UDim2.fromOffset(0, 60), target)
	TweenService:Create(fade, TweenInfo.new(0.5, Enum.EasingStyle.Linear, Enum.EasingDirection.In, 0, false, 0.25),
		{ BackgroundTransparency = 1 }):Play()

	-- The second tween starts from the first's Completed at 0.4 s: 0.1 s into it at 0.5 s.
	local chain = frame("Chain", UDim2.fromOffset(0, 120), target)
	local grow = TweenService:Create(chain, TweenInfo.new(0.4, Enum.EasingStyle.Linear), { Size = UDim2.fromOffset(200, 40) })
	grow.Completed:Connect(function()
		TweenService:Create(chain, TweenInfo.new(0.5, Enum.EasingStyle.Linear), { Position = UDim2.fromOffset(300, 120) })
			:Play()
	end)
	grow:Play()

	-- A legacy tween, Linear over 1 s: halfway at 0.5 s.
	local legacy = frame("Legacy", UDim2.fromOffset(0, 180), target)
	legacy:TweenSize(UDim2.fromOffset(200, 40), Enum.EasingDirection.Out, Enum.EasingStyle.Linear, 1)

	local state = Instance.new("TextLabel")
	state.Name = "SlideState"
	state.Position = UDim2.fromOffset(0, 240)
	state.Size = UDim2.fromOffset(300, 20)
	state.Parent = target
	local connection = RunService.Heartbeat:Connect(function()
		state.Text = "SlideState = " .. slideTween.PlaybackState.Name
	end)

	-- Moves once everything else has stopped, so only its Position changes: where layout
	-- puts it, read from its AbsolutePosition.
	local drift = frame("Drift", UDim2.fromOffset(0, 270), target)
	TweenService:Create(drift, TweenInfo.new(0.3, Enum.EasingStyle.Linear, Enum.EasingDirection.In, 0, false, 1.1),
		{ Position = UDim2.fromOffset(100, 270) }):Play()
	local at = Instance.new("TextLabel")
	at.Name = "DriftAt"
	at.Position = UDim2.fromOffset(0, 320)
	at.Size = UDim2.fromOffset(300, 20)
	at.Parent = target
	drift:GetPropertyChangedSignal("AbsolutePosition"):Connect(function()
		at.Text = `DriftAt = {math.round(drift.AbsolutePosition.X - target.AbsolutePosition.X)}`
	end)
	return function()
		connection:Disconnect()
	end
end
