# sp-edit

A Python script for programmatically reading and editing [Super Productivity](https://super-productivity.com/) tasks via Dropbox sync — no official API required.

## How it works

Super Productivity can sync its full state to Dropbox. To enable this, go to **Settings → Sync & Backup → Sync**, enable syncing, set the provider to Dropbox, and authenticate. You can configure the sync interval (e.g. 1 minute) or trigger it manually.

This script downloads SP's sync file (`Apps/super_productivity/sync-data.json`), modifies it, and uploads it back. SP picks up the change on the next sync.

**Compression:** The sync file is gzip-compressed and base64-encoded when **Settings → Sync & Backup → Sync → Advanced Config → Enable compression** is turned on (recommended for faster transfers). This script assumes compression is enabled.

**Encryption:** SP also supports sync encryption, but enabling it would break this script since the file contents would be unreadable without SP's key.

The tricky part: SP doesn't just read the state blob. It uses a **vector clock + `recentOps` log** for conflict resolution. Simply editing the state and pushing will get overwritten on the next sync. Every change must be accompanied by a proper operation entry in `recentOps` with an incremented vector clock. This script handles all of that transparently.

**Tested against:** Super Productivity v17.4.1 (Flatpak), sync file `schemaVersion: 2`.

> ⚠️ This is unofficial and based on reverse-engineering SP's sync format. A SP update that changes the file format or sync protocol could break it.

## Requirements

- Python 3.8+
- [`rclone`](https://rclone.org/) configured with a Dropbox remote named `dropbox`

To set up rclone with Dropbox:
```bash
rclone config  # follow prompts, name the remote "dropbox"
```

## Usage

```bash
# Inspection — all accept --json for machine-readable output
python3 sp_edit.py dump                            # list all tasks
python3 sp_edit.py dump-today                      # today's tasks with est/spent time
python3 sp_edit.py dump-repeats                    # recurring task configs
python3 sp_edit.py dump-projects                   # all projects
python3 sp_edit.py dump-tags                       # all tags
python3 sp_edit.py dump-project "Project"          # tasks in a project
python3 sp_edit.py dump-tag "Tag"                  # tasks with a tag
python3 sp_edit.py dump-backlog "Project"          # backlog tasks for a project
python3 sp_edit.py dump-notes                      # all notes
python3 sp_edit.py dump-counters                   # simple counters with today's value
python3 sp_edit.py dump-archive                    # archived tasks
python3 sp_edit.py dump-today --json               # example: machine-readable output

# Raw access
python3 sp_edit.py pull                            # download -> /tmp/sp_state.json
python3 sp_edit.py push                            # upload <- /tmp/sp_state.json
python3 sp_edit.py pull-push "<python-expr>"       # one-liner (has `state` variable)

# Tasks
python3 sp_edit.py add-task "Title"                # add to Inbox, scheduled today
python3 sp_edit.py add-task "Title" "Project"      # specific project
python3 sp_edit.py add-task "Title" "Project" 2026-04-01   # specific date
python3 sp_edit.py add-task "Title" "Project" none # unscheduled

python3 sp_edit.py complete-task "Title or ID"
python3 sp_edit.py delete-task "Title or ID"

python3 sp_edit.py update-task "Title or ID" title='"New title"'
python3 sp_edit.py update-task "Title or ID" dueDay='"2026-04-01"'
python3 sp_edit.py update-task "Title or ID" timeEstimate=1800000

python3 sp_edit.py unschedule-task "Title or ID"
python3 sp_edit.py reschedule-task "Title or ID" 2026-04-01

python3 sp_edit.py tag-task "Title or ID" "Tag"
python3 sp_edit.py untag-task "Title or ID" "Tag"

python3 sp_edit.py set-task-notes "Title or ID" "Markdown text"
python3 sp_edit.py clear-task-notes "Title or ID"

python3 sp_edit.py move-to-backlog "Title or ID"
python3 sp_edit.py move-from-backlog "Title or ID"

python3 sp_edit.py move-task-up "Title or ID"
python3 sp_edit.py move-task-down "Title or ID"
python3 sp_edit.py move-task-to-top "Title or ID"
python3 sp_edit.py move-task-to-bottom "Title or ID"

# Subtasks
python3 sp_edit.py add-subtask "Title" "ParentTitle or ID"
python3 sp_edit.py complete-subtask "Title or ID"
python3 sp_edit.py delete-subtask "Title or ID"
python3 sp_edit.py move-subtask "Title or ID" "NewParentTitle or ID"

# Recurring tasks
python3 sp_edit.py add-repeat "Standup" Work DAILY mon,tue,wed,thu,fri 09:30 15
python3 sp_edit.py add-repeat "Weekly review" Inbox WEEKLY fri 16:00 30
python3 sp_edit.py add-repeat "Finances" Household MONTHLY mon

python3 sp_edit.py update-repeat "Standup" startTime='"10:00"'
python3 sp_edit.py update-repeat "Standup" isPaused=true
python3 sp_edit.py delete-repeat "Standup"

# Projects
python3 sp_edit.py add-project "Title"
python3 sp_edit.py update-project "Title or ID" title='"New title"'
python3 sp_edit.py delete-project "Title or ID"       # deletes all tasks too
python3 sp_edit.py archive-project "Title or ID"
python3 sp_edit.py unarchive-project "Title or ID"

# Tags
python3 sp_edit.py add-tag "Title"
python3 sp_edit.py add-tag "Title" "#ff4081"           # with color
python3 sp_edit.py update-tag "Title or ID" title='"New name"'
python3 sp_edit.py delete-tag "Title or ID"            # strips tag from all tasks

# Notes
python3 sp_edit.py add-note "Title"
python3 sp_edit.py add-note "Title" "Project" "Markdown content"
python3 sp_edit.py update-note "Title or ID" content='"Updated text"'
python3 sp_edit.py delete-note "Title or ID"
python3 sp_edit.py pin-note "Title or ID"
python3 sp_edit.py unpin-note "Title or ID"

# Simple counters
python3 sp_edit.py add-counter "Title"                 # type defaults to 'clicks'
python3 sp_edit.py add-counter "Title" number
python3 sp_edit.py increment-counter "Title or ID"
python3 sp_edit.py increment-counter "Title or ID" 3
python3 sp_edit.py decrement-counter "Title or ID"
python3 sp_edit.py set-counter "Title or ID" 5
python3 sp_edit.py delete-counter "Title or ID"

# Batch operations
python3 sp_edit.py complete-done-today                 # complete all of today's tasks
python3 sp_edit.py delete-done-tasks                   # delete all completed tasks
python3 sp_edit.py delete-done-tasks "Project"         # scoped to a project
python3 sp_edit.py move-done-to-archive                # move done tasks to archiveYoung
python3 sp_edit.py restore-task "Title or ID"          # restore from archive
```

### `add-repeat` day syntax

| Argument | Days |
|---|---|
| `mon,tue,wed,thu,fri` | specific days (3-letter abbreviations) |
| `weekdays` | Monday–Friday |
| `all` | every day |

### Global flags

Flags can be combined with any command:

| Flag | Effect |
|---|---|
| `--json` | Machine-readable JSON output (dump-* commands) |
| `--dry-run` | Preview changes without uploading |
| `--no-pull` | Skip download, use cached `/tmp/sp_state.json` |
| `--no-push` | Save changes locally but don't upload |

## Configuration

Override defaults via `~/.sp_edit.conf` (JSON) or environment variables:

```json
{
  "SP_EDIT_REMOTE": "dropbox",
  "SP_EDIT_REMOTE_PATH": "Apps/super_productivity/sync-data.json",
  "SP_EDIT_CLIENT_ID": "C_claud"
}
```

| Env var | Default |
|---|---|
| `SP_EDIT_REMOTE` | `dropbox` |
| `SP_EDIT_REMOTE_PATH` | `Apps/super_productivity/sync-data.json` |
| `SP_EDIT_CLIENT_ID` | `C_claud` |
| `SP_EDIT_LOCAL_RAW` | `/tmp/sp_raw.json` |
| `SP_EDIT_LOCAL_STATE` | `/tmp/sp_state.json` |

## Internals

### File format

```
pf_C2__ + base64(gzip(JSON))
```

### Sync protocol (reverse-engineered)

The JSON has these key fields at the root:

| Field | Purpose |
|---|---|
| `state` | Full app state (tasks, projects, tags, planner, notes, counters, etc.) |
| `recentOps` | Ordered log of the last 500 operations |
| `vectorClock` | Per-client version counters (e.g. `{"desktop": 2290, "mobile": 46}`) |
| `syncVersion` | Monotonically increasing integer, bumped on every push |
| `schemaVersion` | Format version (currently `2`) |

When SP syncs, it replays `recentOps` from remote onto its local state rather than blindly overwriting. This script uses client ID `C_claud` in the vector clock and injects correctly-structured ops for every change.

### Operation codes

| `a` | `o` | `e` | Meaning |
|---|---|---|---|
| `HA` | `CRT` | `TASK` | Create task |
| `HU` | `UPD` | `TASK` | Update task |
| `HDM` | `DEL` | `TASK` | Delete task(s) |
| `RA` | `CRT` | `TASK_REPEAT_CFG` | Create repeat config |
| `RU` | `UPD` | `TASK_REPEAT_CFG` | Update repeat config |
| `HRC` | `DEL` | `TASK_REPEAT_CFG` | Delete repeat config |
| `PA` | `CRT` | `PROJECT` | Create project |
| `PC` | `UPD` | `PROJECT` | Update project |
| `PDM` | `DEL` | `PROJECT` | Delete project |
| `TGA` | `CRT` | `TAG` | Create tag |
| `TGU` | `UPD` | `TAG` | Update tag |
| `TGDM` | `DEL` | `TAG` | Delete tag |
| `NA` | `CRT` | `NOTE` | Create note |
| `NU` | `UPD` | `NOTE` | Update note |
| `NDM` | `DEL` | `NOTE` | Delete note |
| `SCA` | `CRT` | `SIMPLE_COUNTER` | Create counter |
| `SCU` | `UPD` | `SIMPLE_COUNTER` | Update counter |
| `SCDM` | `DEL` | `SIMPLE_COUNTER` | Delete counter |

### Scheduling a task for a specific day

Four things must be updated together:
1. Set `dueDay` on the task entity
2. Add `"TODAY"` to the task's `tagIds`
3. Add the task ID to `tag.entities.TODAY.taskIds`
4. Add the task ID to `planner.days["YYYY-MM-DD"]`
