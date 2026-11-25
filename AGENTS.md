# Project Guidelines & Rules



## Session State Stack (Push / Pop)
 - The root `STATE.md` holds the primary design/project context and must **not** be overwritten when temporarily pivoting to an auxiliary task in a dedicated top-level folder (such as `tools/`).
 - **Push State:** When pivoting to a self-contained sub-task in a top-level folder (e.g., `tools/`), create `<folder>/STATE.md` to track that sub-task's progress, blockers, and next steps while preserving root `STATE.md`.
 - **Pop State:** Once the sub-task is complete or handed back, mark `<folder>/STATE.md` as resolved (or remove/archive it) and resume directly from the root `STATE.md`.
