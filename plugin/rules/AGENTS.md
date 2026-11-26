# EAGLE v6 Design Safety Rules

- Never directly edit `.sch` or `.brd` XML files on disk; doing so can break CadSoft EAGLE v6 forward/back-annotation between schematic and board.
- Route all design edits through `eagle6-mcp`'s `.scr` workflow (`generate_edit_script` → `validate_edit_script` on a staged copy → `save_edit_script`) so the user executes reviewed scripts inside EAGLE GUI with full Undo support.
- For pre-v6 binary EAGLE files, always use `convert_legacy_project` so the original binary files remain untouched.
