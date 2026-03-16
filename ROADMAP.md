# sp-edit Roadmap

This document maps Super Productivity's full feature set against what `sp_edit.py` currently implements, then lays out a phased plan to close the gaps.

## Current Implementation Status

### Implemented

| Command | Description |
|---|---|
| `pull` | Download & decompress sync-data.json from Dropbox |
| `push` | Compress & upload state to Dropbox |
| `pull-push "<expr>"` | One-liner pull → exec Python expr → push |
| `dump` | List all tasks with project, tags, done status |
| `dump-repeats` | List all recurring task configs |
| `add-task` | Create task (project, due date, TODAY tag + planner) |
| `complete-task` | Mark a task as done |
| `delete-task` | Permanently delete a task (cleans project, tags, planner) |
| `update-task` | Modify arbitrary task fields with dueDay side-effects |
| `add-repeat` | Create a recurring task config |
| `update-repeat` | Modify recurring task config fields |
| `delete-repeat` | Delete a recurring task config |

**Sync protocol:** vector clock, `recentOps` log, client ID `C_claud`, `schemaVersion: 2`.

---

## Gap Analysis

The following SP entities and capabilities are not yet covered:

| Area | Entity / Operation | SP State Key |
|---|---|---|
| **Subtasks** | Create, complete, delete, move subtasks | `task.entities[parentId].subTaskIds` |
| **Task tags** | Add / remove tags on a task | `task.tagIds`, `tag.taskIds` |
| **Task description** | Set / clear markdown notes on a task | `task.notes` |
| **Task backlog** | Move task to/from project backlog | `project.backlogTaskIds` |
| **Task ordering** | Reorder tasks within project or tag | `project.taskIds`, `tag.taskIds` |
| **Task reminders** | Schedule time-of-day reminders | `reminder` state, `task.reminderId` |
| **Filtered dumps** | Dump by project / tag / day / backlog | (read-only, no new state writes) |
| **Projects** | Add, update, delete, archive/unarchive | `project.entities` |
| **Tags** | Add, update, delete | `tag.entities` |
| **Notes** | Add, update, delete, pin to today | `note.entities`, `note.todayOrder` |
| **Simple counters** | Dump, increment, decrement, reset | `simpleCounter.entities` |
| **Archive** | List archived tasks; archive done tasks | `archiveYoung` / `archiveOld` |
| **Batch operations** | Complete all done / delete done tasks | multiple task entities |
| **Config / UX** | WebDAV support, dry-run, custom paths | CLI flags |

---

## Phased Roadmap

### Phase 1 — Enhanced Inspection (read-only)
_Goal: make the tool useful for querying without modifying state._

- [ ] `dump-today` — tasks scheduled for today (dueDay = today, or TODAY tag)
- [ ] `dump-project "<Project>"` — tasks (and backlog) for one project
- [ ] `dump-tag "<Tag>"` — tasks carrying a specific tag
- [ ] `dump-backlog "<Project>"` — backlog tasks for a project
- [ ] `dump-projects` — list all projects (id, title, archived, task count)
- [ ] `dump-tags` — list all tags (id, title, task count)
- [ ] `dump-notes` — list all notes (id, title, project, pinned)
- [ ] `dump-counters` — list simple counters with current values
- [ ] `dump-archive` — list archived tasks
- [ ] Add `--json` flag to all `dump-*` commands for machine-readable output

Implementation notes:
- All purely read-only; no new `_make_op` calls needed.
- Wire up to CLI in the `if __name__ == "__main__"` dispatch block.

---

### Phase 2 — Task Enhancements
_Goal: cover common task operations that go beyond basic CRUD._

#### 2a. Subtasks
- [ ] `add-subtask "<Title>" "<ParentTitle|ID>"` — create subtask under a parent
  - Append to `parent.subTaskIds`, set `task.parentId = parent_id`
  - Op: `CRT / TASK / HA` (same as add-task)
- [ ] `complete-subtask "<Title|ID>"` — same as `complete-task` (subtasks are tasks)
- [ ] `delete-subtask "<Title|ID>"` — remove from parent's `subTaskIds` + task entities
- [ ] `move-subtask "<Title|ID>" "<NewParent>"` — reparent a subtask

#### 2b. Task Tagging
- [ ] `tag-task "<Task>" "<Tag>"` — add tag to task
  - Add tag ID to `task.tagIds`; add task ID to `tag.taskIds`
  - Op: `UPD / TASK / HU`
- [ ] `untag-task "<Task>" "<Tag>"` — remove tag from task (reverse of above)

#### 2c. Task Description / Notes
- [ ] `set-task-notes "<Task>" "<Markdown text>"` — set `task.notes` field
  - Op: `UPD / TASK / HU`
- [ ] `clear-task-notes "<Task>"` — set notes to empty string

#### 2d. Backlog Management
- [ ] `move-to-backlog "<Task>"` — move from `project.taskIds` → `project.backlogTaskIds`
  - Op: `UPD / TASK / HU` on task + project
- [ ] `move-from-backlog "<Task>"` — reverse of above

#### 2e. Scheduling Improvements
- [ ] `unschedule-task "<Task>"` — remove dueDay, remove from planner, remove TODAY tag
- [ ] `reschedule-task "<Task>" <YYYY-MM-DD>` — sugar over `update-task` with full side-effects

#### 2f. Task Ordering
- [ ] `move-task-up "<Task>"` — swap with previous in `project.taskIds` / `tag.taskIds`
- [ ] `move-task-down "<Task>"` — swap with next
- [ ] `move-task-to-top "<Task>"`
- [ ] `move-task-to-bottom "<Task>"`

---

### Phase 3 — Projects & Tags CRUD
_Goal: manage the containers that tasks live in._

#### 3a. Projects
- [ ] `add-project "<Title>"` — create new project
  - Populate: `id`, `title`, `taskIds: []`, `backlogTaskIds: []`, `noteIds: []`, `isArchived: false`, `isEnableBacklog: false`, `isHiddenFromMenu: false`, `advancedCfg: {}`
  - Op: `CRT / PROJECT / PA` (infer action code from SP source)
- [ ] `update-project "<Title|ID>" field=value …` — modify project fields
  - Op: `UPD / PROJECT / PU`
- [ ] `delete-project "<Title|ID>"` — remove project and all its tasks
  - Op: `DEL / PROJECT / PDM`
- [ ] `archive-project "<Title|ID>"` — set `isArchived: true`
- [ ] `unarchive-project "<Title|ID>"` — set `isArchived: false`

#### 3b. Tags
- [ ] `add-tag "<Title>" [color]` — create new tag
  - Populate: `id`, `title`, `color`, `taskIds: []`, `advancedCfg: {}`
  - Op: `CRT / TAG / TGA`
- [ ] `update-tag "<Title|ID>" field=value …` — modify tag
  - Op: `UPD / TAG / TGU`
- [ ] `delete-tag "<Title|ID>"` — remove tag; strip from all `task.tagIds`
  - Op: `DEL / TAG / TGDM`

> **Note on op codes:** The script documents task and repeat codes from reverse-engineering. Project, tag, and note op codes (`PA/PU/PDM`, `TGA/TGU/TGDM`, `NA/NU/NDM`) need to be verified against a live sync file or the SP source at `src/app/imex/sync/`. Use `pull-push` with console logging to capture real op codes if unsure.

---

### Phase 4 — Notes
_Goal: manage project-level and global markdown notes._

- [ ] `add-note "<Title>" [project] [--content "<Markdown>"]` — create a note
  - Append to `note.entities`, add ID to `project.noteIds` (or global notes)
  - Op: `CRT / NOTE / NA`
- [ ] `update-note "<Title|ID>" field=value …` — modify note fields
  - Op: `UPD / NOTE / NU`
- [ ] `delete-note "<Title|ID>"` — remove note, clean `project.noteIds`
  - Op: `DEL / NOTE / NDM`
- [ ] `pin-note "<Title|ID>"` — set `isPinnedToToday: true`, prepend to `note.todayOrder`
- [ ] `unpin-note "<Title|ID>"` — set `isPinnedToToday: false`, remove from `todayOrder`

---

### Phase 5 — Simple Counters
_Goal: support SP's habit-tracking counter feature._

Simple counters are stored under `simpleCounter.entities`. Each counter has:
`id`, `title`, `type` (`clicks` or `number`), `countOnDay` (dict of YYYY-MM-DD → value), `order`.

- [ ] `dump-counters` — list counters with today's value _(already listed in Phase 1)_
- [ ] `increment-counter "<Title|ID>" [amount=1]` — add to today's value in `countOnDay`
  - Op: `UPD / SIMPLE_COUNTER / SCA` (verify code)
- [ ] `decrement-counter "<Title|ID>" [amount=1]` — subtract from today's value
- [ ] `set-counter "<Title|ID>" <value>` — set an exact value for today
- [ ] `add-counter "<Title>" [type=clicks]` — create a new counter
- [ ] `delete-counter "<Title|ID>"` — remove counter

---

### Phase 6 — Batch Operations & Quality of Life
_Goal: power-user ergonomics and operational safety._

#### 6a. Batch Task Operations
- [ ] `complete-done-today` — mark all of today's scheduled tasks done
- [ ] `delete-done-tasks [project]` — permanently remove all completed tasks (optional project filter)
- [ ] `move-done-to-archive` — move completed tasks to `archiveYoung` (requires understanding archive state)

#### 6b. CLI / UX Improvements
- [ ] `--dry-run` flag — preview what would be changed without writing or pushing
- [ ] `--no-pull` flag — operate on existing `/tmp/sp_state.json` without re-downloading
- [ ] `--no-push` flag — modify state locally without uploading (useful for scripting)
- [ ] `--json` output flag for all `dump-*` commands (already mentioned in Phase 1)
- [ ] `--verbose` flag — print full task/entity objects instead of one-line summaries

#### 6c. Sync Backend Flexibility
- [ ] WebDAV support — replace `rclone copyto dropbox:…` with configurable rclone remote + path
  - Add `RCLONE_REMOTE` and `REMOTE_PATH` constants (or read from env vars / config file)
- [ ] `~/.sp_edit.conf` — simple INI/JSON config file for remote, paths, client ID overrides

#### 6d. Archive Support
- [ ] `dump-archive` — list tasks in `archiveYoung` / `archiveOld` _(already listed in Phase 1)_
- [ ] `restore-task "<Title|ID>"` — move an archived task back to active state

---

## Op Code Verification Checklist

Before implementing Phase 3–5 operations, verify the correct `a`/`o`/`e` codes by inspecting a live sync file after performing each operation in the SP desktop app:

```
python3 sp_edit.py pull
python3 -c "
import json
with open('/tmp/sp_state.json') as f: s = json.load(f)
for op in s['recentOps'][-5:]:
    print(op['a'], op['o'], op['e'])
"
```

Expected codes to confirm (based on pattern inference):

| Entity | Create | Update | Delete |
|---|---|---|---|
| TASK | `HA` / `CRT` / `TASK` | `HU` / `UPD` / `TASK` | `HDM` / `DEL` / `TASK` |
| TASK_REPEAT_CFG | `RA` / `CRT` / `TASK_REPEAT_CFG` | `RU` / `UPD` / `TASK_REPEAT_CFG` | `HRC` / `DEL` / `TASK_REPEAT_CFG` |
| PROJECT | ? / `CRT` / `PROJECT` | ? / `UPD` / `PROJECT` | ? / `DEL` / `PROJECT` |
| TAG | ? / `CRT` / `TAG` | ? / `UPD` / `TAG` | ? / `DEL` / `TAG` |
| NOTE | ? / `CRT` / `NOTE` | ? / `UPD` / `NOTE` | ? / `DEL` / `NOTE` |
| SIMPLE_COUNTER | ? / `CRT` / `SIMPLE_COUNTER` | ? / `UPD` / `SIMPLE_COUNTER` | ? / `DEL` / `SIMPLE_COUNTER` |

---

## Non-Goals

The following SP features are intentionally out of scope for this CLI tool:

- **Sync encryption** — SP encrypts the blob client-side; without the key the file is opaque.
- **Issue tracker integrations** (Jira, GitHub, GitLab, etc.) — these are cloud-pull features; managing them requires hitting the third-party APIs, not just editing the sync file.
- **Pomodoro / focus-mode state** — transient UI state not persisted to the sync file.
- **Calendar / CalDAV integration** — same as issue integrations; requires external API calls.
- **Metrics / worklog history** — read-only aggregate derived from `timeSpentOnDay`; could be added as a `dump-worklog` command but not a priority.
- **Plugin system** — requires running SP's plugin runtime.

---

## Compatibility Note

This script targets SP v17.4.1 with `schemaVersion: 2`. SP updates may change the sync format. Before upgrading SP, run `pull` and diff the schema to detect breaking changes.
