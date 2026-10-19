-- Code that sizes itself from the screen: the target's size is the area a default
-- ScreenGui gets (below the top bar, inside the device's insets), GetGuiInset reads
-- the top bar, and the camera's ViewportSize is the viewport RHR draws at.
return function(target)
	local screen = target.AbsoluteSize
	local camera = workspace.CurrentCamera.ViewportSize
	local inset = game:GetService("GuiService"):GetGuiInset()
	local bar = Instance.new("Frame")
	bar.Name = "Bar"
	bar.Size = UDim2.fromOffset(screen.X // 2, screen.Y // 2)
	bar.Parent = target
	local label = Instance.new("TextLabel")
	label.Name = "Size"
	label.Position = UDim2.fromOffset(0, 40)
	label.Size = UDim2.fromOffset(200, 30)
	label.Text = `{camera.X}x{camera.Y}`
	label.Parent = target
	local top = Instance.new("TextLabel")
	top.Name = "Inset"
	top.Position = UDim2.fromOffset(0, 80)
	top.Size = UDim2.fromOffset(200, 30)
	top.Text = `{inset.X},{inset.Y}`
	top.Parent = target
	return function()
		bar:Destroy()
		label:Destroy()
		top:Destroy()
	end
end
