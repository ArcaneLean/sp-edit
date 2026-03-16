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
# Inspect
python3 sp_edit.py dump                            # list all tasks
python3 sp_edit.py dump-today                      # list today's tasks with est/spent time
python3 sp_edit.py dump-repeats                    # list all recurring task configs

# Raw access
python3 sp_edit.py pull                            # download -> /tmp/sp_state.json
python3 sp_edit.py push                            # upload <- /tmp/sp_state.json
python3 sp_edit.py pull-push "<python-expr>"       # one-liner (has `state` variable)

# Tasks
python3 sp_edit.py add-task "Title"                # add to Inbox, scheduled today
python3 sp_edit.py add-task "Title" "Project"      # specific project
python3 sp_edit.py add-task "Title" "Project" 2026-04-01   # specific date
python3 sp_edit.py add-task "Title" "Project" none # no scheduling

python3 sp_edit.py complete-task "Title or ID"
python3 sp_edit.py delete-task "Title or ID"

# Update any task field (values are JSON — strings need inner quotes)
python3 sp_edit.py update-task "Title or ID" title='"New title"'
python3 sp_edit.py update-task "Title or ID" dueDay='"2026-04-01"'
python3 sp_edit.py update-task "Title or ID" timeEstimate=1800000

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
```

### `add-repeat` day syntax

| Argument | Days |
|---|---|
| `mon,tue,wed,thu,fri` | specific days (3-letter abbreviations) |
| `weekdays` | Monday–Friday |
| `all` | every day |

## Internals

### File format

```
pf_C2__ + base64(gzip(JSON))
```

### Sync protocol (reverse-engineered)

The JSON has these key fields at the root:

| Field | Purpose |
|---|---|
| `state` | Full app state (tasks, projects, tags, planner, etc.) |
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

### Scheduling a task for a specific day

Four things must be updated together:
1. Set `dueDay` on the task entity
2. Add `"TODAY"` to the task's `tagIds`
3. Add the task ID to `tag.entities.TODAY.taskIds`
4. Add the task ID to `planner.days["YYYY-MM-DD"]`
