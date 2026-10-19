# Known approximations

RHR aims for a useful preview, not a copy of Studio's renderer. This page lists
where its output differs from Roblox, or has not been checked against it. When a
command approximates something at run time, it also says so in its own output
(`notes` on stderr, `fallbacks` / `experimental` in `scene-dump`), so an agent does
not need this page to avoid being misled. It is here so you know what to expect.

"Measured" below means compared with numbers Roblox Studio recorded for the same
file (`tests/studio/`, see its README). Everything else is RHR's best reading of
Roblox's documentation.

## UI layout

**Measured.** Every GuiObject's rectangle comes from RHR's own layout pass
(`src/rhr/ui_layout.py`), checked against Studio on about 450 objects: all within
2 px, except text-sized objects, which get 2 px + 4%.

Covered: UDim2 size and position, AnchorPoint, SizeConstraint, UIPadding,
UISizeConstraint, UIAspectRatioConstraint, UIScale, AutomaticSize (from text and
from children), UIListLayout (sorting, alignment, Wraps, flex, UIFlexItem,
ItemLineAlignment), UIGridLayout (FillDirectionMaxCells, StartCorner, alignment),
UITableLayout (with `FillEmptySpaceColumns`/`Rows`: the free space shared in
proportion to the columns' and rows' own sizes), UIPageLayout (pages one container
length plus Padding apart, the first page showing, as in Studio's edit view; no page
animation), ScrollingFrame canvas, CanvasPosition and scroll bars (below).

Not yet measured against Studio: flex shrink with wrapping, ItemLineAlignment
Stretch, and a UIPageLayout scrolled to another page than the first.

**The top bar.** Screen UI is laid out below Roblox's 58 px top bar
(`ScreenInsets = CoreUISafeInsets`, the default), as in a running game. Studio's
edit view has no top bar: pass `--topbar-height 0` to match it. `None` and
`DeviceSafeInsets` use the whole viewport (a desktop has no notch).
`TopbarSafeInsets` is not modelled; it falls back to `CoreUISafeInsets` with a
note on stderr. A story's UI gets the area a game's own UI gets in Play (measured in
Studio's phone emulator on 2026-10-18): its `target` is a default ScreenGui's area,
below the top bar and inside a phone's safe area, and `GuiService:GetGuiInset()`
returns the top bar. The camera's `ViewportSize` is still the whole screen, where
Studio's leaves out the notches. `GuiService.TopbarInset` is the whole top bar
between the device's side insets: RHR draws none of Roblox's top-bar buttons, where
in Roblox the free area starts after them (about 208 px from the left in Studio's
phone emulator).

**Phone notches** (`--device phone`, `--device android`). Measured in Studio's iPhone
16 emulator in Play on 2026-10-18; tests/test_notch_fill.py rebuilds each case. Two
ScreenGui properties decide what is painted beside the notches. Neither moves
anything, and under `ScreenInsets = None` neither applies.

- `SafeAreaCompatibility` (FullscreenExtension, the default): an object whose rect,
  with its outline (BorderSizePixel) and a Border UIStroke, covers the device safe
  area on both axes paints out to the screen edges. Its background, outline and
  stroke reach the screen edges, its image stretches to fill, a UICorner rounds the
  new corners, and a ClipsDescendants clip stretches with it. Its AbsolutePosition,
  AbsoluteSize and children's layout stay as they were. The safe area runs up behind
  the top bar, so in a default ScreenGui only an object that reaches up there
  stretches: a full-size Frame stays between the notches. An object that covers the
  safe area on one axis only does not stretch.
- `ClipToDeviceSafeArea` (on by default) clips everything that does not stretch to
  the safe area, a stretched object's children included. Roblox's docs say it clips
  every descendant; in Studio a stretched object is not clipped.

Not measured, and drawn by the rule RHR picked: `SafeAreaCompatibility = None`
(nothing stretches, as Roblox documents it); the phones' 21 px home-bar inset (treated
like a notch: stretched over, and clipped above); the corner pixels of a stretched
UIStroke; an outline that is not drawn (under a UICorner, or with a transparent
background), which does not count; a Contextual UIStroke on a Frame, which counts like
a Border one. In a stretched object, what is sized by the object follows the
stretched rect (UICorner, a UIStroke's Scale thickness, UIGradient, ImageLabel
ScaleType, a CanvasGroup), while its text, scroll bars and a ViewportFrame's 3D view
keep its own rect and are not clipped to the safe area. A rotated object is tested by
its unrotated rect, and the clip is in screen space. Clicks (`rhr hitmap`) use the
object's own rect.

**ScrollingFrame.** Measured in Studio on 2026-10-18 (tests/test_scroll_scale.py and
tests/test_scroll_bars.py hold the cases): within 1.5 px of Studio on every one.

- A child's Scale resolves against the canvas (AbsoluteCanvasSize less the
  UIPadding), not the frame. CanvasSize's own Scale resolves against the frame's
  parent, as the frame's Size does.
- A scroll bar shows on an axis ScrollingDirection allows when the canvas is longer
  than the frame, less the other bar's strip when that one shows. Each bar takes a
  ScrollBarThickness strip from the window: the children are clipped to the rest, and
  the strip shows the frame's background. ScrollBarInset decides whether the canvas
  leaves the strip out; VerticalScrollBarPosition Left puts the vertical bar on the
  left. ScrollingEnabled false still draws the bars.
- The thumb is the window's share of the track, at least two thicknesses long, placed
  by CanvasPosition's share of the scroll range.
- Roblox's own bar images (the defaults) cannot be shipped with RHR, so the bar they
  make is drawn as a shape, measured to match: ScrollBarImageColor3 at half opacity,
  with round ends. A custom TopImage, MidImage or BottomImage is drawn from its asset
  id as Studio draws it: the top image over the thumb's first ScrollBarThickness, the
  bottom one over its last, the middle one stretched between; a horizontal bar turns
  each a quarter turn counter-clockwise. A bar image RHR cannot draw is left out, with
  no stand-in, and listed as any image is (Images, below): another file the Roblox
  client ships, one of Roblox's own bar images on a different part, a `rbxthumb://`
  thumbnail, an asset id not downloaded, or a link RHR does not read.

Not measured, and drawn by the rule RHR picked: UIPadding's Scale in a ScrollingFrame
(against the frame, as everywhere else); AutomaticCanvasSize with Scale-sized children
(their extent taken against the canvas before it grows); bars inside the frame's
UICorner (clipped to it); ScrollBarThickness, CanvasSize and CanvasPosition under a
UIScale (scaled like other pixel sizes); a track shorter than two thicknesses; content
beside a left bar that is not inset (clipped to the window); a ScrollingFrame as a
UITableLayout cell.

**Several ScreenGuis** are drawn one per pass and stacked by `DisplayOrder`. A
disabled or empty ScreenGui is skipped by every command. In a place file, only
StarterGui's ScreenGuis are on screen: ones kept in ReplicatedStorage, ServerStorage
and the like are templates that scripts clone in at run time, so they are left out
and named on stderr (`--all-guis` draws them). A model file draws every ScreenGui. UI outside any ScreenGui
(Studio's own plugin models are built that way) is drawn as a bottom layer with no
top-bar inset.

**ZIndexBehavior** is followed in drawing, and `rhr hitmap` and `rhr check`'s
`button-blocked` stack objects by the same rules, so the picture and the hit map agree
on which object is on top. Measured in Studio on 2026-10-19
(tests/test_zindex_behavior.py holds the cases):

- `Global` (the default for a ScreenGui, BillboardGui or SurfaceGui made by
  `Instance.new`) stacks every object in the gui by ZIndex, ties in tree order: a
  child with a lower ZIndex than its parent goes behind it, and cousins interleave. A
  ClipsDescendants frame and a ScrollingFrame's window still clip their descendants,
  and a ScrollingFrame's bars draw at the frame's own place in the order.
- `Sibling` (the ScreenGui a story is mounted in, as UI Labs mounts stories) stacks
  children above their parent, and siblings by ZIndex.
- Under both, ties stack in child order: a UIListLayout or UIGridLayout places its
  items by LayoutOrder but does not stack them by it.
- Under `Global` a CanvasGroup is not composited. Its GroupTransparency and
  GroupColor3 fade and tint its own background only, and its descendants are drawn
  untinted, at full opacity and unclipped by it (or its UICorner). Their hit regions
  are still clipped to its rect, so what overflows a CanvasGroup is drawn but not hit,
  in Studio as in RHR.

Not followed: under `Sibling`, RHR fades a CanvasGroup's own UIStroke with the group
and cuts an Outer one off at the group's edge, where Studio draws it whole and opaque.
Not measured, and drawn by the rule RHR picked: a CanvasGroup's UIGradient under
`Global` (applied to its own background) and its border under either behavior (faded
with its background, and under `Sibling` also cut off at the group's edge); `Global`
in a BillboardGui or SurfaceGui (the ScreenGui rules). UI outside any ScreenGui is
drawn as `Sibling`.

## Text

**Measured:** Roblox makes `TextSize` the full line height (ascent + descent), not
the font's em size, and RHR does the same for drawing, TextScaled fitting,
wrapping, truncation and AutomaticSize. Heights match Studio exactly; widths within
about 1.3% on average: like Roblox, every glyph's advance is rounded up to a whole
pixel, which makes small text noticeably wider than the font's own metrics (Builder
Sans at 16 px: 126 px for a 19-character line, where the exact advances give 116;
measured with TextService over five families at TextSize 8 to 100).

A label's text is not clipped to the label: unwrapped text longer than its box runs
past it, as in Studio (left-aligned to the right, centred both ways, right-aligned
to the left). A ClipsDescendants ancestor still clips it.

Known differences:

- Widths are still off by a pixel or two per line now and then, so a line that only
  just overflows its box in Studio can still fit in RHR (or the other way round) and
  wrap differently. RHR's bundled Roboto is a different version from the one Studio
  ships, which accounts for some of it.
- TextTruncate draws a one-character ellipsis (`…`) where Roblox's docs show `...`,
  a 1-5 px difference. Where exactly Roblox cuts has not been measured.
- `MaxVisibleGraphemes` is not drawn (it is a typewriter effect over time);
  `rhr check` reports it instead.
- Right-to-left text with a non-default `LineHeight` keeps the default spacing.
- A symbol no bundled font has (`✕`, `✓`, `★`, `▶` and their neighbours) is drawn
  from a symbol font that comes with the operating system (Segoe UI Symbol, Apple
  Symbols, DejaVu Sans), as Roblox uses the system's fonts, so its exact shape
  depends on the machine. On a machine without such a font it draws as an empty box. Set
  `RHR_SYSTEM_FONT_FALLBACK=0` to never use system fonts.
- Fonts: RHR uses the fonts of a local Roblox or Studio install when there is one
  (stderr says which), then bundled open-licence copies of the builds Roblox ships
  (Source Sans Pro, Roboto, and others), then look-alikes. Builder Sans and other
  faces that cannot be redistributed fall back to a look-alike without an install.
  Set `RHR_ROBLOX_FONTS=0` to always use the bundled fonts.

## Images

Images are drawn from the local cache. `ui` and `scene` first download the ones the
file uses that are not cached, as the Roblox Studio user (the original file, at full
size); `preview` downloads the world's and its in-world UI's, not its ScreenGuis'.
`--offline` skips that. Without a Studio login an image comes from Roblox's thumbnail
service instead, at most 420 px, which puts sprite-sheet crops (`ImageRectOffset`,
measured in the original's pixels) in the wrong place. ScrollingFrame bar images have
their own rules (ScrollingFrame, under UI layout).

An image RHR cannot draw leaves its area empty, with no stand-in, and the report's
`missingAssets` lists it with the reason: an asset id not downloaded (`offline` with
`--offline`), one Roblox refused, a file built into the Roblox client (`rbxasset://`),
which the UI renderer does not read, a `rbxthumb://` thumbnail, which Roblox makes at
run time, or a link RHR does not read. Only an image the picture would show is listed:
not a hidden or fully transparent one, one clipped away or off the screen, a
HoverImage or PressedImage, or an empty Image or id 0, which Roblox draws as nothing
too. A BillboardGui's or SurfaceGui's images are listed when its own picture leaves
them out, whether or not the camera sees it. Each row names the instance (`path`,
`class`), the part of the screen the image would cover (`rect`, in screen pixels: the
bounding box of a rotated or in-world one, cut to what the screen and any clipping
frame show) and, where RHR can say, how to get it drawn (`hint`); with
`scene --views`, the view it is missing from (`view`). A 3D asset's row (a mesh, a
decal) has no `rect`, and a ViewportFrame's 3D content is not listed.

`rhr check` draws the UI without downloading anything and reports each image its
render leaves out as `image-missing`, with the same reason and hint: a warning for an
image Roblox refuses for good (shown as unavailable, no such asset, not an image),
which is blank in Roblox too, and info for one only RHR's render leaves out (a file
built into the client, a thumbnail, a link RHR does not read, a download that failed
on RHR's side). An id not downloaded yet is not reported; `rhr ui` downloads it. A
HoverImage or PressedImage Roblox refused, on a visible element, is reported the same
way, though no picture shows it.

`ResampleMode` (Default = smooth, Pixelated = nearest) is honoured for Stretch, Fit
and Crop. Tile and Slice filtering have not been checked.

## Clickable regions (`rhr hitmap`)

Uses the same rectangles as `rhr layout`. An element counts as interactive when it
is a button, a TextBox, or has `Active` or `Selectable` set. Each report probes the
centre of every interactive element and names the topmost `Active` element as the
target. A hidden (`Visible = false`) `Active` element is kept on purpose: an
invisible element that swallows clicks is exactly the bug this command is for.

## 3D scenes

`rhr scene` and `rhr preview` draw a static authoring preview with THREE.js in
a headless Chromium-family browser (Chrome, Edge, Brave, Chromium, or Chrome for
Testing's headless shell; the `--json` report names it). They all draw the same
page; the tests pin the headless shell for identical pixels.

**What is drawn:** in a place file, the world (Workspace, Lighting, StarterGui's
in-world UI). Models stored in ServerStorage, ReplicatedStorage, ReplicatedFirst,
ServerScriptService, StarterPack and StarterPlayer are not drawn, as in a running game
until a script clones them in; a note counts them, and `--focus` on one draws it. A
model file draws everything. A place is drawn as saved: parts a script hides or moves
at run time (a map's "invisible" walls saved opaque) show as they are in the file.

**Measured:** part positions, sizes and rotations (`rhr scene-dump`) match Studio.
Compared with Studio screenshots of the same scene, geometry, camera framing,
shadow direction and the default sky match.

**Model.Scale** is recorded, not applied. `Model:ScaleTo()` rewrites every part's
size and position, so a saved file already holds the scaled geometry (checked on a
scaled model that ships with Studio).

**Compared side by side with Studio** (a swatch of 16 materials, a brick wall, a
union and terrain, same camera, default lighting; with Roblox Studio installed and
signed in, see below):

- Materials use Roblox's own texture maps (colour, normal, roughness, metalness),
  downloaded by the asset ids Roblox publishes (`src/rhr/scene/roblox_materials.json`,
  from its creator docs). The colour map's alpha says where the part's Color applies:
  Brick's bricks take the colour and the mortar keeps its own, as in Studio. Textures
  tile every 10 studs. `MaterialService.Use2022Materials` picks the current or the
  pre-2022 set; a model file (no MaterialService) uses the current one. Metals follow
  `Lighting.EnvironmentSpecularScale`: at 0 they read as their colour, as in Studio; at
  1 they reflect the sky. A part's MaterialVariant uses its own maps, tinted by the
  part's Color and tiled at its StudsPerTile, once they are cached. Glass-like
  materials are see-through.
- Neon is unlit and drawn about 3x brighter than its colour; bright Neon glows in its
  own colour (a blurred quarter-resolution copy added over the picture, as Roblox
  does it) and dim Neon does not. Transparent Neon is see-through by its
  Transparency, with less glow. (In Studio a strongly transparent Neon part reads
  more solid than that; RHR keeps what is behind it visible.) Partly transparent Neon fades by its Transparency
  (brightness x (1 - T), glow x (1 - T)^2); at T = 0.3 it is still brighter and more
  saturated than Studio's, which shows more of what is behind it (README picture:
  mean difference 50 of 255 on the red bars). Additive particle effects also read
  whiter than Studio's. Compared with Studio at
  its highest quality level; at low quality levels Studio draws no glow at all. Unknown materials draw as Plastic and are
  counted as `materialFallbacks`. `--flat-materials` draws plain colours.
- Plastic has Roblox's faint surface relief, and legacy surfaces (`TopSurface =
  Studs`, Inlet, Weld, Glue, Universal on block Parts of Plastic or SmoothPlastic) are
  drawn with the install's surface textures, 2 studs per tile.
- With no Sky, the sky is Roblox's default one from the install. A Sky's faces are
  stretched onto squares as Roblox does, whatever the images' own sizes.
- Unions are drawn with the render mesh Studio saved: downloaded by the union's
  AssetId (modern places) or read from the file (older ones), with each source part's
  colour unless UsePartColor is set. A union made in a Studio session and exported
  before the place was saved has neither; it is drawn as its outlined bounding box
  and counted as a geometry fallback.
- Terrain is meshed smooth from the place's voxels (surface nets: the surface crosses
  between a solid and an empty voxel as far as the solid one's occupancy reaches),
  with Roblox's terrain textures for each face direction (top, side, bottom), 8 studs
  per tile, coloured by the material's base colour and the place's MaterialColors.
  Where two materials meet they are blended, the way Studio does it on nine pairs
  measured: the material earlier in Roblox's terrain order (Grass, Slate, Concrete,
  Brick, Sand, ...) reaches half a voxel (2 studs) into the other, and the seam is a
  ragged band about 1.5 studs wide, shaped by each texture's height (its colour
  map's alpha) and a fine noise. Studio's edge follows its textures more closely
  (grass blades poking into sand); RHR's is softer. Steep slopes fade from a
  material's top texture to its side texture over a band of slope. Grass came out a
  little brighter and yellower than Studio's, rock a little lighter; in a place with
  EnvironmentDiffuseScale 0 (old default lighting), faces turned from the sun are
  much lighter than Studio's. Cliff faces are smooth where Studio's are bumpy.
  Water waves are not drawn.
- Terrain grass (Terrain.Decoration) is drawn at rest; Roblox sways it, wind or not.
  Blades grow on the Grass material's top faces, fitted to Studio at the highest
  quality with GrassLength 0.7: blade heights, how much of a side view they cover at
  each height, their colour (the place's Grass MaterialColor, about 0.6 as bright as
  a flat part of that colour, varying per blade), and how they fade with distance
  (gone by about 200 studs). Up close Studio's grass reads as a carpet, so the
  ground under it is darkened toward the blade colour too, fading out by 150 studs.
  Studio's blades are finer and closer in tone to the ground than RHR's; far away
  (150-250 studs) RHR's grass still shows a little more than Studio's. GrassLength
  scales blade length; the density change Roblox makes with it is not modelled.

**Without Roblox Studio** on the machine (or signed out): images are 420 px
thumbnails, meshes and unions are outlined boxes, materials use public-domain (CC0)
ambientCG look-alikes (`src/rhr/scene/materials/credits.json`) at 4-10 studs per
tile, the default sky is a gradient, and there is no plastic relief or stud texture.
stderr says so on every 3D render.

**Approximate, by eye:**

- Lighting in modern places (`EnvironmentDiffuseScale` above 0, as every current
  Roblox template has) is fitted to Studio: a calibration rig (white, grey, dark and
  coloured blocks, a pillar, an overhang, panels 25 to 800 studs away) built under a
  Roblox template's lighting, captured in Studio at its highest quality level and
  rendered by RHR at the same cameras; the sun strength, sky light, ambient, sky
  brightness, fog colour, exposure and tone curve were searched to minimise the
  difference (on average about 8/255 per channel over 35 sampled regions, from 22
  before). The model: the sun with shadows; light from the sky as drawn (Atmosphere
  veil included), which gives shadows and shaded faces Roblox's sky-blue colour;
  sky visibility on a 4-stud voxel grid, as Roblox computes it, so the floor under an
  overhang, the wall behind a pillar or the inside of a room get less sky light than
  open ground; Ambient / OutdoorAmbient as a little flat light; and a per-channel
  tone curve, so very bright colours drift toward white as Roblox's do. Sky
  visibility treats a part as covering the cells it overlaps (meshes and unions by
  their bounding box, weighted down), so thin or open meshes block more sky than they
  should, and a room lower than about 4 studs is too coarse for the grid.
  `ExposureCompensation` is applied.
- Older places (`EnvironmentDiffuseScale` 0) keep the earlier model, set by eye and
  matched against Studio's legacy lighting: ambient plus a sky-coloured hemisphere
  light and the sun.
- Shadows from the sun are on by default, as in Studio (`--no-shadows` turns them
  off). Two shadow cascades cover the view out to 500 studs from the camera: sharp
  near it, coarser further away; nothing casts shadows beyond that. On the GPU they
  cost a few percent of render time.
- Post-processing (experimental): `BloomEffect` (what is brighter than its Threshold,
  blurred by its Size, added at its Intensity) and `ColorCorrectionEffect` (Brightness,
  Contrast, Saturation, TintColor) are drawn, set by eye; Studio's own at low quality
  levels draws neither. `DepthOfFieldEffect` and `BlurEffect` are not drawn and are
  listed under `unsupportedVisualClasses`.
- `SunRaysEffect` is drawn as screen-space light scattering: a glow around the sun
  (narrower and brighter at low Spread), blurred toward the sun through what is sky,
  so anything in front of the sun casts a long shadow through it, plus a haze over
  objects. Fitted to Studio at the highest quality (a bar half across the sun,
  Intensity 0.1 and 0.25, Spread 0.1, 0.3 and 1) on how much light it adds at each
  distance from the sun, on the open and the shadowed side. Studio's fine spokes near
  the sun are not reproduced, and objects in front of the sun come out a little
  lighter than in Studio. It still shows with the sun just off screen, as in Studio.
- `Clouds` are drawn as one still layer in the sky, from the flat cloud tile Roblox
  ships for devices without 3D textures (so only with Studio installed; without it
  they are listed as unsupported). Fitted to Studio at the highest quality looking
  25 degrees up, per band of sky: how much the clouds cover, how big they look and how
  bright they are, at Cover 0.35 to 1 and Density 0.2 to 1. Cover opens the layer
  steeply (clear below about 0.4, overcast from 0.8), Density sets how opaque they
  are, Color tints them. Roblox's clouds are volumetric and change shape over time
  even with no wind; RHR's are flatter, with less of the puffy detail. They darken
  after sunset by a set amount rather than following the Lighting.
- The sky's top face (SkyboxUp, and Roblox's default sky) is turned a quarter to
  match Studio; the bottom face is as it was (unverified).
- The sun is drawn (Sky.SunTextureId, or Roblox's own from the install), exactly
  where Lighting:GetSunDirection() puts it, under the clouds, sized by
  SunAngularSize; its disc and soft rim were matched to Studio's default sun seen
  straight up. The moon and stars are not drawn.
- Point, Spot and Surface lights: colour, brightness, range and angle are used;
  intensity is not calibrated. At most the 16 most relevant (nearest the camera,
  weighted by range and brightness) are drawn, because each light costs every pixel;
  a note says how many were left out.
- Atmosphere, measured in Studio with black and white panels 25 to 800 studs away at
  Density 0.2, 0.375 and 0.6 and Haze 0, 2 and 5: geometry fades as
  exp(-(depth / L)^p), with L and p rising steeply with Density (at 0.2 almost
  nothing fades, at 0.6 everything is gone by 200 studs); other densities are
  interpolated. Haze veils the sky: everything below the horizon once Haze reaches
  1, a band above the horizon that widens with Haze, the whole sky from Haze 5.
  `Offset` and `Glare` are not drawn. In an automatic view (`--view`, `--focus`),
  which stands far back from a whole map, the fog is capped so the build stays
  readable. A Sky whose six faces are not all cached draws the default sky.
  The sun, moon and stars are not drawn. With several Sky objects the first one is
  used; which one Roblox picks has not been checked.
- Decals and Textures need their images cached. Face orientation was checked in
  Studio. A decal on a mesh (a face on an R6 head) is projected onto the mesh's
  own surface. Images the client ships (`rbxasset://textures/face.png`) come from the
  Studio install.
- A mesh's own image (a MeshPart's `TextureID`, a FileMesh or Head SpecialMesh's
  `TextureId`) is drawn with the mesh's UVs; the part's colour shows through its
  transparent parts, and a SpecialMesh's `VertexColor` tints it.
- Characters (a Model with a Humanoid), compared with Studio on R6 and R15 rigs,
  plain and dressed, from the front and back: `Shirt`, `Pants` and `ShirtGraphic`
  are painted onto the body with the layouts Roblox itself uses (from the Studio
  install), over the body's colour; R6 bodies use Roblox's rounded body part meshes
  and a body package's `CharacterMesh` meshes; the R6 head is the classic head mesh
  (a `Head` SpecialMesh, sized as measured in Studio); `BodyColors` colours the body
  parts. A body part with its own image (a body package, R6 or R15) wears no
  classic clothing, as in Studio; a head with its own image shows no face decal.
  Layered clothing is fitted to the body through its cages (reference cage to the
  body's cages, matched by UV; layers stacked in Order on each other's outer cage):
  close to Studio's shape, not exact. Old version 1 meshes keep V from the bottom
  (checked on old hats and an R6 package). Without a Studio install, clothing is not
  drawn. Not modelled: poses (a rig stands as saved; animations are never played)
  and facial animation.

**Drawn as stand-ins, and reported as such:**

- MeshParts and FileMeshes use cached mesh files, downloaded before a render with
  the Studio login (Roblox serves most meshes only to a signed-in account). Every mesh
  format is read, including versions 6 and 7 (version 7 is Draco-compressed; RHR
  ships Google's decoder); only the most detailed level of detail is drawn. A mesh file
  that cannot be read is drawn as a box and a note says so. A MeshPart
  with its mesh is drawn with its SurfaceAppearance maps through the mesh's UVs
  (AlphaMode Transparency cuts out, Overlay shows the part colour through; normal,
  roughness and metalness maps are used). Without the mesh it is a placeholder: its
  bounding box with an outline, no shadow, coloured from the SurfaceAppearance image,
  counted as a geometry fallback. Skinned meshes, bones and LOD are not modelled.

## Rendering speed and the GPU

3D renders use the machine's GPU through the browser's WebGL, which is about eight
times faster than software rendering (a textured test scene: 2 s instead of 17 s).
Pixels can then differ slightly between GPUs: on the development machine a GPU render
differed from a software one on 0.13% of pixels, by 0.4/255 on average.
`RHR_WEBGL=software` draws on the CPU (SwiftShader) for identical pixels everywhere;
the tests and CI use it. A machine without a usable GPU falls back to software by
itself.

The first 3D render starts a warm worker (a browser with the 3D page loaded), which
later renders reuse; it stops after 10 idle minutes. A render on the kept page is
pixel for pixel the same as one on a fresh page (tests/test_kept_page.py).
`RHR_PROFILE=1` prints where a command's time went.

## In-world UI (BillboardGui, SurfaceGui)

The GUI inside them is laid out and drawn as screen UI is, on the canvas size
Roblox would give it. BillboardGui placement and size match Studio's camera
projection (measured in play mode). SurfaceGui face orientation was measured in
Studio for every face.

Approximate: a panel partly hidden behind geometry is drawn whole or not at all (one
ray to its anchor decides). Canvases larger than 4096 px per side are clamped.
`LightInfluence` and `Brightness` are not applied.

A ScrollingFrame here scrolls as on screen. Measured in Studio on 2026-10-19 in a
SurfaceGui and a BillboardGui (tests/test_inworld_scroll.py holds the cases): each
frame's window, canvas, CanvasPosition, children and scroll bars came out as in a
ScreenGui, and RHR draws them by the same rules (ScrollingFrame, under UI layout).

## ViewportFrame

The 3D content is drawn with the same scene renderer and placed at the frame's
rectangle. Supported: parts, the frame's own `CameraCFrame` or a child Camera,
Ambient, LightColor, LightDirection, ImageColor3 and ImageTransparency. Not
supported: shadows, Sky, post-processing and GUI objects inside the frame, and
`missingAssets` does not list a mesh or texture its content leaves out. Not yet
compared with Studio.

## Effects

Particles, Beams and Trails are drawn inside the 3D scene as one still frame. The aim
is that an agent sees whether an effect is there, where, how big, what colour and
whether it glows; not the exact particles Roblox would draw.

- **Playing an effect.** Scripts are not run. Most VFX keep their emitters disabled
  and a script plays them with `:Emit()`; the community convention stores how in
  attributes: `EmitCount` (emitted at once), `EmitDelay` (seconds after the start) and
  `EmitDuration` (seconds switched on at `Rate`). RHR reads these and plays the effect
  itself. An Enabled emitter runs the whole time, already full at the start. A
  disabled emitter without these attributes is not drawn and is named in the output.
  Other attributes (tweened sizes, `TimeScale_*` curves and the like) are ignored.
- **Which moment.** By default, the middle of the stretch where the most particle area
  is on show (the output says which moment); `--effect-time T` picks another.
- **Randomness** is seeded per emitter (`--seed`), so the same file gives the same
  picture, but particle positions are not the ones Roblox would pick.
- **Size and shape**, measured in Studio: a particle is 2 x `Size` across; `Squash` s
  stretches one axis by 1 + |s| and shrinks the other as much (taller for s > 0,
  wider for s < 0). `SpreadAngle` X turns the direction about the part's X axis and Y
  about the axis across X and the direction (a Back emitter with (0, 60) fans out
  flat). A Disc's `ShapePartial` is how much of the radius emits, from the rim in. An
  emitter without a `Texture`, or whose texture cannot be loaded, draws nothing, and a
  particle aligned to its velocity (`VelocityParallel` / `VelocityPerpendicular`) draws
  nothing while it has none, as in Roblox. Transparency sequences are clamped to 0..1.
- **Blending and brightness**, fitted to a sweep of flat particles in Studio
  (`LightEmission` -2..1, `Brightness` 1/5/25, transparency 0/0.5/0.75, over black and
  white; 9/255 RMS end to end): each colour channel is capped softly near 2.5, alpha
  acts as alpha^1.45, `LightEmission` 1 adds light and below 0 darkens what is behind
  hard, and the result goes through Studio's tone curve, which turns very bright
  colours toward white (bright orange turns yellow, then white). In a scene without
  Lighting, the particles alone are blended this way and put back over the picture.
  The fit is to a default Baseplate in Studio; other Lighting shifts it. `ZOffset`
  moves particles toward the camera, keeping their size on screen.
- **Background**: a file without Lighting is drawn on RHR's plain dark background
  (32, 36, 43). Studio shows such a model over whatever place it is in, usually
  darker, so dark smoke that reads light grey against Studio's backdrop can read dark
  against RHR's. The effect itself is drawn the same.
- **LightInfluence** (particles, Beams and Trails), measured in Studio with flat
  particles and beams under 15 lightings (212 readings, 1.7/255 RMS): it blends
  `Brightness` toward the scene's light by the square root of `LightInfluence`, so at
  1 `Brightness` no longer counts. The scene's light is the larger of `Ambient` and
  `OutdoorAmbient`, squared, plus `Lighting.Brightness` / 2 while the sun is up; the
  way the effect faces does not matter. In daylight a lit effect looks much like an
  unlit one; at night it goes almost black (the moon gives a few percent), and in the
  hour or so before sunrise it is black (sunset is taken to mirror sunrise, which was
  measured). Not drawn: the yellow tint for the first 15 minutes of sunlight, local lights, and shade (an effect
  indoors or under a roof is lit as if outdoors). Without Lighting, daylight.
- **Framing**: without a Camera or `--view`, the view covers visible parts and the
  bulk of the particles (5th to 95th percentile), not invisible holder parts or a few
  sparks flung far away.
- **Drawn**: emission from parts (Box, Sphere, Cylinder, Disc shapes) and attachments
  (a point), following their rotation; `EmissionDirection`, `SpreadAngle`, `Speed`,
  `Acceleration`, `Drag`, `TimeScale`, rotation, size, colour, transparency and
  `Squash` over lifetime, flipbooks, and every `Orientation`.
- **Not applied**: size and transparency envelopes, `LockedToPart`, wind, `VelocityInheritance`
  (parts do not move in a still frame). Fire, Smoke, Sparkles and Explosion are not
  drawn.
- **Built-in textures** (`rbxasset://textures/particles/...`) are read from the Studio
  install, `.dds` files included. Side by side with Studio, the sparkle (the default
  texture), smoke and square textures match within a few levels; `fire_main.dds` is
  drawn darker (about a fifth of Studio's glow); the faint explosion smoke and
  forcefield glow textures are within 7 levels. Without a Studio install they are not
  drawn, like any texture that cannot be loaded, and the output names them.
- **Beam**: curve, widths, segments, colour, texture and `LightEmission` are drawn.
  The texture's vertical axis runs along the beam, the image's top at `Attachment0`;
  `Stretch` repeats it `TextureLength` times, `Wrap` every `TextureLength` studs, and
  `TextureSpeed` scrolls it toward `Attachment1` by that many textures per second of
  the effect time (all measured in Studio). The scroll's starting point in Studio
  depends on when the beam appeared, so only its direction and speed can be matched.
- **Highlight**: the fill and the outline (about 3 px) are drawn, over everything
  (`AlwaysOnTop`) or only where seen (`Occluded`); fills first in order, then every
  outline, as Studio does. Only the front faces make the shape, so holes in a mesh get
  their own outline. The first four Highlights are exact; later ones get a plain fill.
- **Trail**: built from the parent part's saved velocity. A trail with no saved
  motion is reported as unsupported rather than guessed. The image's top is at the
  attachments (the newest end); `Wrap` tiles start there, `Static` ones at the oldest
  point drawn (measured in Studio).

## Reading files

RHR reads binary files (`.rbxm`, `.rbxl`) itself (`rhr.rbx`, a port of rbx-dom's
reader and of the Lune script, with the reflection database of the pinned Lune) and
XML files with Lune and rbx-dom; both give the same result, checked on every fixture
and on real places (tests/test_rbx_reader.py). `RHR_READER=lune` reads binary files
with Lune too. A class that rbx-dom's database does not know
(newer than its build, or plugin-only) is read from the file's XML: simple values
(booleans, numbers, text) are recovered; enums, references and structured values
such as UDim2 and Color3 are listed in that node's `unreadable` list, so the element
may draw without its size or colour and the output says which properties are
missing.

A part that is fully transparent (Transparency 1) is not drawn at all, so it does not
hide effects behind or inside it. A Sky or Atmosphere counts only inside Lighting, as
in Roblox; one saved elsewhere in a model changes nothing.

## Not done at all

Scripts, physics, animation and anything else that happens at run time. A UI that a
script builds or moves is previewed as it is saved in the file.

## Hit map: who gets a click

Measured in Studio on 2026-09-28 (a solo playtest, simulated left clicks at each
button's centre, `Activated` counted on every button; 27 cases, kept as
tests/fixtures/hitmap_studio.rbxmx). `rhr hitmap` and `rhr check`'s `button-blocked`
follow these rules; they are exact for the cases measured, and the rest is inferred:

- A button (TextButton, ImageButton; RHR treats a TextBox the same) gets clicks when it
  and every ancestor are Visible and Interactable.
- Within one ScreenGui the topmost such button under the pointer gets the click. A
  Frame, TextLabel or ImageLabel over it never takes it, Active or not, at any ZIndex;
  a button with Interactable false passes it through.
- A visible, Interactable, Active non-button in a ScreenGui with a higher DisplayOrder
  swallows the click for the ScreenGuis below, even at BackgroundTransparency 1 or in a
  CanvasGroup at GroupTransparency 1. Hidden, non-Active or non-Interactable ones, and
  those in a disabled ScreenGui or a lower DisplayOrder, do not.
- Not measured: two ScreenGuis with equal DisplayOrder (RHR takes the later one as on
  top), `Modal`, `Selectable`/gamepad selection, touch input, and a button with Active
  false (RHR treats it like any button).

## Devices (`--device`)

Measured in Studio's device emulator on 2026-09-28 (a playtest client per preset: the
camera's viewport, where a full-size Frame lands under each ScreenInsets mode, the
touch controls' AbsolutePosition and size); rhr.devices holds the numbers. The top
bar is 58 px on every device measured; phones in landscape have notch insets on both
sides (iPhone 16: 59 px; Galaxy A16: 47 px) and a 21 px home bar. Not modelled:
portrait, the on-screen keyboard, console "title safe" margins, the thumbstick's
exact dead zones (the check uses the frame Roblox reserves for it), and changes to
Roblox's touch controls after that date.

What is painted beside the notches was measured later, in Play on 2026-10-18 (Phone
notches, under UI layout). That emulator's iPhone 16 screen was 874x401, with 62 px
notches and no home-bar inset; RHR applies the rule to each preset's own insets.

**Story-time input and GUI reads** (`rhr layout` and the other story commands). A
story reads a Studio play-test's values for the members UI code uses, which follow the
preset where they differ: `console` has Gamepad1 connected
(`GetConnectedGamepads`, `GetGamepadConnected`, `IsNavigationGamepad`,
`GetNavigationGamepads`, a list of 18 `GetSupportedGamepadKeyCodes`) and
`IsTenFootInterface` is true; the other presets have no gamepad and a false
`IsTenFootInterface`. On every preset `TouchControlsEnabled` and the navigation flags
start true, nothing is pressed or focused, the sensor and VR flags are false
(Studio's phone emulator reads them false), and `IsWindows` is true (the host OS).
`GetStringForKeyCode` gives a US keyboard's characters and
`GetImageForKeyCode` the default controller's `rbxasset://` image for a gamepad
button, `""` for any other key; both were read from Studio on 2026-10-19 in Edit
mode, so a console's own controller art, and other keyboard layouts, are not modelled.
Studio's `GetNavigationGamepads` lists all eight pads with none connected; RHR lists
the connected ones. The gamepad buttons `ButtonCenter`, `ButtonBack` and the four
`ButtonUp` to `ButtonRight` have images in Studio but are missing from Lune's
KeyCode enum, so a story cannot name them.

Still errors in a story, as these members do for a script in Roblox:
`GuiService.DisplayScalingMode`, `SelectedCoreObject`, `ViewportSizeInMM`,
`GetBrickCount`, `GetScreenResolution`, `GetSafeZoneOffsets`, `IsMemoryTrackerEnabled`;
`UserInputService.BottomBarSize`, `NavBarSize`, `RightBarSize`, `StatusBarSize`,
`LegacyInputEventsEnabled`, `OnScreenKeyboardAnimationDuration`,
`OverrideMouseIconBehavior`, `TouchScreenEnabled` and `GetPlatform` (Roblox restricts
them to its own scripts); `GuiService:GetClosestDockPart` and
`UserInputService:GetUserCFrameEnabled` (no such members).
Roblox answers these, but RHR still raises "not a valid member" because Lune cannot
create an InputObject: `UserInputService:GetDeviceAcceleration`, `GetDeviceGravity`,
`GetDeviceRotation` and `GetGamepadState`.

