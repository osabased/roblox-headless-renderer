--!strict
-- A loop that waits forever and changes nothing: the capture stops at the cap and
-- names where its timer waits.
return function(target: Frame)
	local polls = 0
	task.spawn(function()
		while true do
			task.wait(0.5)
			polls += 1
		end
	end)
	local label = Instance.new("TextLabel")
	label.Name = "Label"
	label.Text = "polling"
	label.Parent = target
end
