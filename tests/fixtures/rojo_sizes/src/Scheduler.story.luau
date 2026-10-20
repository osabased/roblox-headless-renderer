--!strict
-- When the story's timers fire and what its clock reads, counted in frames from mount.
local RunService = game:GetService("RunService")

return function(target: Frame)
	local frame = 0
	local start = os.clock()
	local values: { [string]: string } = {
		DeferFrame = "pending",
		DelayFrame = "pending",
		WaitElapsed = "pending",
		CancelledDelay = "not fired",
		ClockFrames6To30 = "pending",
	}
	local clockAt: { [number]: number } = {}

	local report = Instance.new("Frame")
	report.Name = "Report"
	report.Size = UDim2.fromScale(1, 1)
	report.Parent = target
	local layout = Instance.new("UIListLayout")
	layout.SortOrder = Enum.SortOrder.LayoutOrder
	layout.Parent = report
	local rows: { [string]: TextLabel } = {}
	for order, name in { "DeferFrame", "DelayFrame", "WaitElapsed", "CancelledDelay", "ClockFrames6To30" } do
		local label = Instance.new("TextLabel")
		label.Name = name
		label.LayoutOrder = order
		label.Size = UDim2.new(1, 0, 0, 20)
		label.TextXAlignment = Enum.TextXAlignment.Left
		label.Parent = report
		rows[name] = label
	end
	local function refresh()
		for name, label in rows do
			label.Text = name .. " = " .. values[name]
		end
	end

	local counter = RunService.PreRender:Connect(function()
		frame += 1
	end)
	task.defer(function()
		values.DeferFrame = tostring(frame)
	end)
	task.delay(0.25, function()
		values.DelayFrame = tostring(frame)
	end)
	task.spawn(function()
		local elapsed = task.wait(0.1)
		values.WaitElapsed = string.format("%.4f at frame %d", elapsed, frame)
	end)
	local cancelled = task.delay(0.1, function()
		values.CancelledDelay = "fired"
	end)
	task.cancel(cancelled)
	local heartbeat = RunService.Heartbeat:Connect(function()
		if frame == 6 or frame == 30 then
			clockAt[frame] = os.clock() - start
		end
		if clockAt[6] and clockAt[30] then
			values.ClockFrames6To30 = string.format("%.4f", clockAt[30] - clockAt[6])
		end
		refresh()
	end)
	refresh()
	return function()
		counter:Disconnect()
		heartbeat:Disconnect()
		report:Destroy()
	end
end
