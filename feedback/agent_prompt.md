# QA repair summary

1. ERROR `layout_overlap` at `step_draw_triangle`: Visible objects overlap: side_a, side_b
   ID: `qa-911ac432d015` Scope: `visual_action`
   Repair: Move one of ['side_a', 'side_b'] to a different layout slot/position, or split the overlapping writes into separate steps.
2. ERROR `layout_overlap` at `step_draw_triangle`: Visible objects overlap: side_a, side_c
   ID: `qa-80ffbdf185d5` Scope: `visual_action`
   Repair: Move one of ['side_a', 'side_c'] to a different layout slot/position, or split the overlapping writes into separate steps.
3. ERROR `layout_overlap` at `step_draw_triangle`: Visible objects overlap: side_b, side_c
   ID: `qa-a8516e82a047` Scope: `visual_action`
   Repair: Move one of ['side_b', 'side_c'] to a different layout slot/position, or split the overlapping writes into separate steps.
4. ERROR `layout_overlap` at `step_vertices`: Visible objects overlap: dot_A, side_b
   ID: `qa-0901c18c81b3` Scope: `visual_action`
   Repair: Move one of ['dot_A', 'side_b'] to a different layout slot/position, or split the overlapping writes into separate steps.
5. ERROR `layout_overlap` at `step_vertices`: Visible objects overlap: dot_A, side_c
   ID: `qa-8e6e8fa5027c` Scope: `visual_action`
   Repair: Move one of ['dot_A', 'side_c'] to a different layout slot/position, or split the overlapping writes into separate steps.
