# Derivative Geometry Rendering Fix Plan

## Background

The example `examples/derivative_geometric_meaning/` generates a short teaching video explaining the geometric meaning of the derivative.

The intended lesson is mathematically standard:

- Draw a smooth curve `y=f(x)`, concretely `f(x)=x^2`.
- Mark a fixed point `P=(a,f(a))`.
- Mark a moving point `Q=(a+h,f(a+h))`.
- Show the secant slope `(f(a+h)-f(a))/h`.
- Let `h -> 0`, so the secant approaches the tangent at `P`.
- Conclude that `f'(a)` is the tangent slope.

The rendered final frame exposes two issues:

1. The curve is visually a polyline, not a smooth function graph.
2. The final formula overlaps with the plot area, especially near the x-axis.

This document records the root causes and a staged fix plan.

Important scope note:

- Layout fixes solve the formula/plot overlap only. They do not change the curve, which remains a polyline unless Issue 1 is addressed.
- Denser polyline sampling makes the curve visually smoother, but it is still a polyline approximation.
- Native `FunctionGraph` / `AxesPlot` support is the correct fix for preserving smooth function-graph semantics.

## Issue 1: Curve Is Not Mathematically Smooth

### Current Behavior

The storyboard asks for a smooth curve:

```text
Draw the curve y=f(x)=x^2 as a smooth curve on the axes.
```

But the generated scene represents the curve as multiple `Line` mobjects:

```json
{"id": "curve_0", "type": "Line", "args": {"start": [-1.5, 2.25, 0], "end": [-1.0, 1.0, 0]}}
{"id": "curve_1", "type": "Line", "args": {"start": [-1.0, 1.0, 0], "end": [-0.5, 0.25, 0]}}
...
```

The generated Manim code mirrors this:

```python
mobj_curve_0 = Line(mobj_axes.c2p(-1.5, 2.25), mobj_axes.c2p(-1.0, 1.0))
mobj_curve_1 = Line(mobj_axes.c2p(-1.0, 1.0), mobj_axes.c2p(-0.5, 0.25))
...
```

At `P=(1,1)`, this creates a visual corner:

- Left segment slope from `(0.5,0.25)` to `(1.0,1.0)` is `1.5`.
- Right segment slope from `(1.0,1.0)` to `(1.5,2.25)` is `2.5`.
- The intended tangent slope for `f(x)=x^2` at `a=1` is `2`.

So the tangent line itself is numerically correct for `x^2`, but the curve shown under it is not differentiable at the sampled point as a drawn polyline.

### Root Cause

The current DSL mobject registry supports only basic primitives such as `Line`, `Dot`, `Axes`, `Tex`, and `Text`. It does not support a semantic function graph object such as `FunctionGraph`, `ParametricFunction`, or `Axes.plot`.

As a result, a function curve is approximated by hand-authored coordinates and line segments. Mathematical consistency depends entirely on the generator choosing enough samples and matching all related geometry manually.

The existing `coordinate_space: "plane"` mechanism is still useful for future graph objects: it already maps plane coordinates through the referenced axes via `axes.c2p(...)`. New semantic mobjects should reuse this coordinate transform path instead of introducing a separate mapping system.

### Short-Term Fix

Use denser polyline sampling when a smooth function graph is requested.

Requirements:

- Sample `f(x)=x^2` with enough points to visually remove corners.
- Add extra samples near important points such as `a`, `a+h`, and intermediate `h` values.
- Keep all point coordinates on the same function definition.
- Compute tangent and secant endpoints from the same function metadata, not from independently guessed coordinates. This includes `secant_line`, intermediate secants such as `secant_h03` and `secant_h015`, and `tangent_line`.

This is a pragmatic fallback while the DSL lacks native function graphs.

Expected result:

- The rendered curve should look smooth enough for teaching video use.
- The internal representation is still multiple `Line` segments.
- Strict mathematical smoothness is not guaranteed at segment joins, though dense sampling should make visible corners negligible.

### Medium-Term Fix

Add a semantic function graph mobject to the DSL.

Example DSL shape:

```json
{
  "id": "curve",
  "type": "FunctionGraph",
  "args": {
    "function": "x**2",
    "x_range": [-1.5, 1.8],
    "axes": "axes"
  },
  "style": {
    "stroke_color": "TEAL",
    "stroke_width": 5
  }
}
```

Compile it to Manim through `axes.plot(...)`.

Expected result:

- The curve is generated as a function graph rather than hand-authored line segments.
- The visual output and the DSL semantics both represent a smooth curve.
- This is the first stage that should be considered a real fix for the curve smoothness issue, not just a visual approximation.

The DSL should also support function-derived points and lines:

- `PointOnFunction`: compute `(x, f(x))`.
- `SecantLine`: compute the line through `(a,f(a))` and `(a+h,f(a+h))`.
- `TangentLine`: compute slope from symbolic derivative or numeric derivative.

This would prevent drift between the curve, points, secants, and tangent.

## Issue 2: Formula Overlaps with Plot Area

### Current Behavior

The axes are centered and large:

```json
{
  "id": "axes",
  "type": "Axes",
  "args": {
    "x_range": [-1.8, 2.2, 1],
    "y_range": [-0.5, 3.8, 1],
    "width": 7.5,
    "height": 5.0
  },
  "layout": {"slot": "main"}
}
```

The compiler places the main slot at the center of the frame. With `height=5.0`, the axes occupy approximately `y=-2.5` to `y=2.5` in frame coordinates.

The final formula is placed by absolute coordinates:

```json
{
  "id": "limit_line1",
  "position": {"mode": "absolute", "point": [0.0, -2.1, 0]}
}
{
  "id": "limit_line2",
  "position": {"mode": "absolute", "point": [0.0, -2.8, 0]}
}
```

The first formula line therefore lands inside the axes region.

There is also a coordinate mapping issue: because `y_range` starts at `-0.5`, the mathematical x-axis `y=0` maps to a visual position around `y=-1.9`, very close to the first formula line at `y=-2.1`.

### Root Cause

The layout system already defines a `bottom_formula` slot, but this example does not use it for the final derivative formula. Instead, the scene mixes:

- `layout.slot: "main"` for the axes.
- Absolute frame coordinates for final formula lines.
- A caption slot below them.

This bypasses the existing slot-based layout mechanism and makes it possible for formulas to be placed inside the plot area.

The static layout QA is also not tuned for coordinate plots:

- It flags normal `Axes` and curve overlap as layout errors, even though curves should be drawn on axes.
- It does not strongly catch `Tex/Text` overlapping the axes or plot content in the final frame.
- The static layout estimate for `Tex` uses a low-confidence heuristic. The repository already has render-probe infrastructure for more accurate TeX bounding boxes, but this example's static QA path does not rely on it strongly enough to block the overlap.

### Short-Term Fix

Use explicit vertical partitioning for this example:

- Move the plot upward.
- Reduce the axes height.
- Place the final formula in the existing `bottom_formula` slot.
- Avoid absolute y coordinates for formula placement.

Recommended layout:

- Use the existing `bottom_formula` slot for the derivative formula.
- Keep the caption in the existing `caption` slot.
- Keep axes and plot-attached objects in the main plot area, with enough vertical clearance from `bottom_formula`.

For this example:

- Replace `position.mode: "absolute"` on `limit_line1` and `limit_line2` with slot-based placement, or merge them into one formula object using `layout: {"slot": "bottom_formula"}`.
- Reduce axes height from `5.0` to around `4.0` or `4.2`.
- Move axes center upward, for example to `y=0.45`.
- Put the complete derivative formula into one `Tex` object when possible:

```tex
f'(a)=\lim_{h\to0}\frac{f(a+h)-f(a)}{h}
```

This reduces vertical stacking and makes slot-based fitting easier.

### Medium-Term Fix

Add plot-aware layout semantics.

The planner/compiler should understand that a math plot scene has distinct regions:

- Plot region.
- Annotation region.
- Formula region.
- Caption region.

Rules:

- `Axes`, function graphs, points, secants, and tangent lines belong to the plot region.
- Final formulas belong to the formula region.
- Captions belong to the caption region.
- Absolute positions should be rejected or warned when a text/formula object falls inside an occupied plot region.

### QA Improvements

Adjust static layout QA for math plot scenes:

1. Downgrade or ignore normal overlap between `Axes` and plot-attached geometry:
   - `Axes` + `Line`
   - `Axes` + `Dot`
   - `Axes` + `FunctionGraph`
   - `Axes` + `Arrow`

2. Strengthen checks for text/formula overlap, including the final rendered frame:
   - `Tex/Text` overlapping `Axes`
   - `Tex/Text` overlapping `FunctionGraph`
   - `Tex/Text` overlapping secant/tangent lines
   - `Tex/Text` too close to x-axis or y-axis tick labels
   - After the last step, formulas intersecting the plot region
   - After the last step, the formula baseline too close to the x-axis

3. Wire the existing render-probe / Manim-derived bounding box infrastructure into this QA path for `Tex`, instead of relying only on the static string-length heuristic.

## Recommended Implementation Order

1. Fix formula/layout overlap first.
   - Use the existing `bottom_formula` slot for final formulas.
   - Stop placing final formulas with hard-coded absolute coordinates unless the position is validated against the plot region.
   - Keep final formulas out of the `main` plot region.
   - Move or shrink axes in this example.
   - Expected effect: the final formula no longer overlaps the axes or curve.
   - Non-effect: the curve remains a polyline.

2. Improve curve representation with a short-term polyline fallback.
   - Start with denser polyline sampling.
   - Add samples near derivative/tangent points.
   - Keep all geometric objects derived from the same function metadata.
   - Expected effect: the curve appears visually smoother.
   - Limitation: the curve is still composed of `Line` segments.

3. Add semantic function graph support for the real curve fix.
   - Introduce `FunctionGraph` or `AxesPlot`.
   - Compile to Manim `axes.plot`.
   - Add semantic point/secant/tangent helpers.
   - Expected effect: the curve is represented as a smooth function graph, and related geometry is derived from the same function definition.

4. Improve QA.
   - Implement the QA Improvements listed above.
   - Keep final-frame formula/plot overlap detection in that QA path, not as a separate implementation track.

## Acceptance Criteria

For `examples/derivative_geometric_meaning/`:

- The visible curve should appear smooth near `P`.
  - Manual acceptance: no visible corner or kink at normal preview resolution.
  - Optional automated acceptance for polyline fallback: adjacent segment angle change near `P` should stay below a chosen threshold, for example `< 1°`, or the fallback should be replaced by `FunctionGraph` / `AxesPlot`.
- `P`, `Q`, intermediate `Q` positions, secants, and tangent should all be consistent with `f(x)=x^2`.
- The tangent at `P=(1,1)` should have slope `2`.
- The final formula should not overlap the axes, curve, x-axis, tangent line, or point labels.
- Static QA should not report normal axes/curve overlap as a blocking error.
- Static or visual QA should report a blocking issue if a final formula is placed inside the plot region.
