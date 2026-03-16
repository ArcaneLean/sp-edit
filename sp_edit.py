#!/usr/bin/env python3
"""
Super Productivity Dropbox editor.
Downloads sync-data.json from Dropbox, decompresses it, lets you edit,
then recompresses and uploads back so both desktop and phone SP pick it up.

Usage:
    python3 sp_edit.py dump
        Print all tasks.

    python3 sp_edit.py dump-repeats
        Print all recurring task configs.

    python3 sp_edit.py pull
        Download latest from Dropbox -> /tmp/sp_state.json

    python3 sp_edit.py push
        Compress /tmp/sp_state.json and upload to Dropbox.

    python3 sp_edit.py pull-push "<python-expr>"
        Pull, apply expression (has `state` var), push in one step.

    python3 sp_edit.py add-task "Title" [project] [YYYY-MM-DD|none]
        Add a task. Project defaults to Inbox, date defaults to today.
        Use 'none' to add without scheduling.

    python3 sp_edit.py complete-task "Title or ID"
        Mark a task as done.

    python3 sp_edit.py delete-task "Title or ID"
        Permanently delete a task.

    python3 sp_edit.py update-task "Title or ID" field=value [field=value ...]
        Update task fields. Values are parsed as JSON (strings need quotes).
        Example: update-task "Buy milk" title='"Buy oat milk"' dueDay='"2026-03-20"'

    python3 sp_edit.py add-repeat "Title" project cycle days [start_time] [estimate_min]
        Create a recurring task.
        cycle:      DAILY | WEEKLY | MONTHLY
        days:       comma-separated: mon,tue,wed,thu,fri,sat,sun  (or 'all' / 'weekdays')
        start_time: HH:MM  (optional, default none)
        estimate_min: integer minutes (optional, default 0)
        Example: add-repeat "Standup" Work DAILY mon,tue,wed,thu,fri 09:30 15

    python3 sp_edit.py update-repeat "Title or ID" field=value [field=value ...]
        Update a recurring task config fields.

    python3 sp_edit.py delete-repeat "Title or ID"
        Delete a recurring task config.
"""

import base64, gzip, json, subprocess, sys, time, random, string, uuid
from pathlib import Path
from datetime import date

DROPBOX_PATH = "dropbox:Apps/super_productivity/sync-data.json"
LOCAL_RAW    = "/tmp/sp_raw.json"
LOCAL_STATE  = "/tmp/sp_state.json"
PREFIX       = "pf_C2__"
CLIENT_ID    = "C_claud"

DAY_FIELDS   = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAY_ALIASES  = {
    "mon": "monday", "tue": "tuesday", "wed": "wednesday", "thu": "thursday",
    "fri": "friday",  "sat": "saturday", "sun": "sunday",
}


# ---------------------------------------------------------------------------
# Core I/O
# ---------------------------------------------------------------------------

def pull():
    """Download and decompress from Dropbox -> /tmp/sp_state.json"""
    print("Downloading from Dropbox...")
    subprocess.run(["rclone", "copyto", DROPBOX_PATH, LOCAL_RAW], check=True)
    with open(LOCAL_RAW, "r") as f:
        raw = f.read().strip()
    idx = raw.index("H4sI")
    b64 = raw[idx:]
    data = base64.b64decode(b64 + "==")
    parsed = json.loads(gzip.decompress(data))
    with open(LOCAL_STATE, "w") as f:
        json.dump(parsed, f, indent=2)
    print(f"State written to {LOCAL_STATE}")
    return parsed


def push():
    """Compress /tmp/sp_state.json and upload to Dropbox"""
    with open(LOCAL_STATE, "r") as f:
        parsed = json.load(f)

    parsed["lastModified"] = int(time.time() * 1000)
    parsed["syncVersion"] = parsed.get("syncVersion", 0) + 1

    compressed = gzip.compress(json.dumps(parsed, separators=(",", ":")).encode())
    b64 = base64.b64encode(compressed).decode()
    payload = PREFIX + b64

    with open(LOCAL_RAW, "w") as f:
        f.write(payload)

    print("Uploading to Dropbox...")
    subprocess.run(["rclone", "copyto", LOCAL_RAW, DROPBOX_PATH], check=True)
    print("Done. SP will sync within 60 seconds.")


def _save(parsed):
    with open(LOCAL_STATE, "w") as f:
        json.dump(parsed, f, indent=2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_op(parsed, o, e, a, action_payload, primary_id, all_ids=None):
    """Build and append a recentOps entry, incrementing the vector clock."""
    vc = parsed.setdefault("vectorClock", {}).copy()
    vc[CLIENT_ID] = vc.get(CLIENT_ID, 0) + 1
    parsed["vectorClock"] = vc

    op = {
        "id": str(uuid.uuid4()),
        "a": a,
        "o": o,
        "e": e,
        "p": {"actionPayload": action_payload, "entityChanges": []},
        "c": CLIENT_ID,
        "v": vc,
        "t": int(time.time() * 1000),
        "s": 2,
        "d": primary_id,
        "ds": all_ids if all_ids is not None else [primary_id],
        "sv": parsed.get("syncVersion", 0),
    }

    ops = parsed.setdefault("recentOps", [])
    ops.append(op)
    if len(ops) > 500:
        parsed["recentOps"] = ops[-500:]


def _find_project(state, name):
    projects = state["project"]["entities"]
    pid = next(
        (pid for pid, p in projects.items() if p["title"].lower() == name.lower()),
        None,
    )
    if pid is None:
        print(f"Error: project '{name}' not found.")
        print("Available:", [p["title"] for p in projects.values()])
        sys.exit(1)
    return pid


def _find_task(state, title_or_id):
    """Find a task by exact ID, then exact title (case-insensitive), then partial title."""
    tasks = state["task"]["entities"]
    if title_or_id in tasks:
        return title_or_id, tasks[title_or_id]
    needle = title_or_id.lower()
    exact = [(tid, t) for tid, t in tasks.items() if t["title"].lower() == needle]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        print(f"Error: multiple tasks match '{title_or_id}':")
        for tid, t in exact:
            print(f"  {tid}  {t['title']}")
        sys.exit(1)
    partial = [(tid, t) for tid, t in tasks.items() if needle in t["title"].lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        print(f"Error: multiple tasks partially match '{title_or_id}':")
        for tid, t in partial:
            print(f"  {tid}  {t['title']}")
        sys.exit(1)
    print(f"Error: no task found matching '{title_or_id}'")
    sys.exit(1)


def _find_repeat(state, title_or_id):
    cfgs = state["taskRepeatCfg"]["entities"]
    if title_or_id in cfgs:
        return title_or_id, cfgs[title_or_id]
    needle = title_or_id.lower()
    matches = [(rid, r) for rid, r in cfgs.items() if r.get("title", "").lower() == needle]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Error: multiple repeat configs match '{title_or_id}':")
        for rid, r in matches:
            print(f"  {rid}  {r['title']}")
        sys.exit(1)
    partial = [(rid, r) for rid, r in cfgs.items() if needle in r.get("title", "").lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        print(f"Error: multiple repeat configs partially match '{title_or_id}':")
        for rid, r in partial:
            print(f"  {rid}  {r['title']}")
        sys.exit(1)
    print(f"Error: no repeat config found matching '{title_or_id}'")
    sys.exit(1)


def _parse_kvs(args):
    """Parse key=value pairs, values interpreted as JSON (wrap strings in quotes)."""
    changes = {}
    for arg in args:
        if "=" not in arg:
            print(f"Error: expected key=value, got '{arg}'")
            sys.exit(1)
        k, v = arg.split("=", 1)
        try:
            changes[k] = json.loads(v)
        except json.JSONDecodeError:
            changes[k] = v  # treat as plain string fallback
    return changes


def _new_task_id():
    return "".join(random.choices(string.ascii_letters + string.digits + "_-", k=21))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def dump():
    if not Path(LOCAL_STATE).exists():
        pull()
    with open(LOCAL_STATE) as f:
        parsed = json.load(f)
    tasks = parsed["state"]["task"]["entities"]
    projects = {p["id"]: p["title"] for p in parsed["state"]["project"]["entities"].values()}
    tags = {t["id"]: t["title"] for t in parsed["state"]["tag"]["entities"].values()}
    for tid, t in tasks.items():
        proj = projects.get(t.get("projectId"), "")
        tag_names = [tags.get(x, x) for x in t.get("tagIds", [])]
        done = "✓" if t.get("isDone") else " "
        print(f"[{done}] {t['title']:<50} project={proj}  tags={tag_names}  id={tid}")


def dump_repeats():
    if not Path(LOCAL_STATE).exists():
        pull()
    with open(LOCAL_STATE) as f:
        parsed = json.load(f)
    cfgs = parsed["state"]["taskRepeatCfg"]["entities"]
    projects = {p["id"]: p["title"] for p in parsed["state"]["project"]["entities"].values()}
    for rid, r in cfgs.items():
        proj = projects.get(r.get("projectId"), "")
        days = [d[:3] for d in DAY_FIELDS if r.get(d)]
        time_str = f" @{r['startTime']}" if r.get("startTime") else ""
        est = r.get("defaultEstimate", 0)
        est_str = f" est={est // 60000}m" if est else ""
        paused = " [PAUSED]" if r.get("isPaused") else ""
        print(f"{r['title']:<45} {r.get('repeatCycle','?'):<8} {','.join(days):<25} project={proj}{time_str}{est_str}{paused}  id={rid}")


def add_task(title, project_name="Inbox", due_date=str(date.today())):
    parsed = pull()
    state = parsed["state"]
    now_ms = int(time.time() * 1000)

    project_id = _find_project(state, project_name)
    task_id = _new_task_id()

    task = {
        "id": task_id,
        "subTaskIds": [],
        "timeSpentOnDay": {},
        "timeSpent": 0,
        "timeEstimate": 0,
        "isDone": False,
        "title": title,
        "tagIds": ["TODAY"] if due_date else [],
        "created": now_ms,
        "attachments": [],
        "projectId": project_id,
    }
    if due_date:
        task["dueDay"] = due_date

    _make_op(parsed, "CRT", "TASK", "HA", {
        "task": task,
        "workContextId": "TODAY" if due_date else project_id,
        "workContextType": "TAG" if due_date else "PROJECT",
        "isAddToBacklog": False,
        "isAddToBottom": False,
    }, task_id)

    state["task"]["entities"][task_id] = task
    state["task"]["ids"].append(task_id)
    state["project"]["entities"][project_id]["taskIds"].append(task_id)
    if due_date:
        state["tag"]["entities"]["TODAY"]["taskIds"].append(task_id)
        state["planner"]["days"].setdefault(due_date, []).append(task_id)

    _save(parsed)
    push()
    print(f"Added task '{title}' to '{project_name}'" + (f" scheduled for {due_date}" if due_date else ""))


def complete_task(title_or_id):
    parsed = pull()
    state = parsed["state"]

    task_id, task = _find_task(state, title_or_id)

    _make_op(parsed, "UPD", "TASK", "HU", {
        "task": {"id": task_id, "changes": {"isDone": True}},
    }, task_id)

    task["isDone"] = True

    _save(parsed)
    push()
    print(f"Completed task '{task['title']}'")


def delete_task(title_or_id):
    parsed = pull()
    state = parsed["state"]

    task_id, task = _find_task(state, title_or_id)

    _make_op(parsed, "DEL", "TASK", "HDM", {
        "taskIds": [task_id],
    }, task_id)

    # Remove from entities and ids
    del state["task"]["entities"][task_id]
    if task_id in state["task"]["ids"]:
        state["task"]["ids"].remove(task_id)

    # Remove from project
    proj_id = task.get("projectId")
    if proj_id and proj_id in state["project"]["entities"]:
        task_ids = state["project"]["entities"][proj_id].get("taskIds", [])
        if task_id in task_ids:
            task_ids.remove(task_id)

    # Remove from all tags
    for tag in state["tag"]["entities"].values():
        if task_id in tag.get("taskIds", []):
            tag["taskIds"].remove(task_id)

    # Remove from planner
    for day_tasks in state["planner"]["days"].values():
        if task_id in day_tasks:
            day_tasks.remove(task_id)

    _save(parsed)
    push()
    print(f"Deleted task '{task['title']}'")


def update_task(title_or_id, changes):
    parsed = pull()
    state = parsed["state"]

    task_id, task = _find_task(state, title_or_id)

    # Handle scheduling side-effects when dueDay changes
    new_due = changes.get("dueDay")
    if new_due and new_due != task.get("dueDay"):
        if "TODAY" not in task.get("tagIds", []):
            task.setdefault("tagIds", []).append("TODAY")
            changes["tagIds"] = task["tagIds"]
        today_tag = state["tag"]["entities"].get("TODAY")
        if today_tag and task_id not in today_tag.get("taskIds", []):
            today_tag.setdefault("taskIds", []).append(task_id)
        state["planner"]["days"].setdefault(new_due, [])
        if task_id not in state["planner"]["days"][new_due]:
            state["planner"]["days"][new_due].append(task_id)

    _make_op(parsed, "UPD", "TASK", "HU", {
        "task": {"id": task_id, "changes": changes},
    }, task_id)

    task.update(changes)

    _save(parsed)
    push()
    print(f"Updated task '{task['title']}': {changes}")


def add_repeat(title, project_name, repeat_cycle, days_str, start_time=None, estimate_min=0):
    parsed = pull()
    state = parsed["state"]
    now_ms = int(time.time() * 1000)

    project_id = _find_project(state, project_name)
    repeat_id = _new_task_id()

    # Parse days
    if days_str.lower() == "all":
        active_days = {d: True for d in DAY_FIELDS}
    elif days_str.lower() == "weekdays":
        active_days = {d: d not in ("saturday", "sunday") for d in DAY_FIELDS}
    else:
        selected = {DAY_ALIASES.get(d.strip(), d.strip()) for d in days_str.split(",")}
        active_days = {d: d in selected for d in DAY_FIELDS}

    cfg = {
        "id": repeat_id,
        "title": title,
        "projectId": project_id,
        "tagIds": [],
        "repeatCycle": repeat_cycle.upper(),
        "quickSetting": repeat_cycle.upper(),
        "repeatEvery": 1,
        "repeatFromCompletionDate": False,
        "isPaused": False,
        "defaultEstimate": estimate_min * 60000,
        "startDate": str(date.today()),
        "order": 0,
        "shouldInheritSubtasks": False,
        "disableAutoUpdateSubtasks": False,
        "subTaskTemplates": [],
        **active_days,
    }
    if start_time:
        cfg["startTime"] = start_time
        cfg["remindAt"] = "AtStart"

    _make_op(parsed, "CRT", "TASK_REPEAT_CFG", "RA", {
        "taskRepeatCfg": cfg,
    }, repeat_id)

    state["taskRepeatCfg"]["entities"][repeat_id] = cfg
    state["taskRepeatCfg"]["ids"].append(repeat_id)

    _save(parsed)
    push()
    days_active = [d for d in DAY_FIELDS if active_days.get(d)]
    print(f"Created repeat '{title}' in '{project_name}' ({repeat_cycle}, {days_active})")


def update_repeat(title_or_id, changes):
    parsed = pull()
    state = parsed["state"]

    repeat_id, cfg = _find_repeat(state, title_or_id)

    _make_op(parsed, "UPD", "TASK_REPEAT_CFG", "RU", {
        "taskRepeatCfg": {"id": repeat_id, "changes": changes},
    }, repeat_id)

    cfg.update(changes)

    _save(parsed)
    push()
    print(f"Updated repeat '{cfg['title']}': {changes}")


def delete_repeat(title_or_id):
    parsed = pull()
    state = parsed["state"]

    repeat_id, cfg = _find_repeat(state, title_or_id)

    _make_op(parsed, "DEL", "TASK_REPEAT_CFG", "HRC", {
        "taskRepeatCfgId": repeat_id,
    }, repeat_id)

    del state["taskRepeatCfg"]["entities"][repeat_id]
    if repeat_id in state["taskRepeatCfg"]["ids"]:
        state["taskRepeatCfg"]["ids"].remove(repeat_id)

    _save(parsed)
    push()
    print(f"Deleted repeat '{cfg['title']}'")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dump"

    if cmd == "pull":
        pull()
    elif cmd == "push":
        push()
    elif cmd == "dump":
        dump()
    elif cmd == "dump-repeats":
        dump_repeats()
    elif cmd == "add-task" and len(sys.argv) > 2:
        title    = sys.argv[2]
        project  = sys.argv[3] if len(sys.argv) > 3 else "Inbox"
        raw_date = sys.argv[4] if len(sys.argv) > 4 else str(date.today())
        due      = None if raw_date.lower() == "none" else raw_date
        add_task(title, project, due)
    elif cmd == "complete-task" and len(sys.argv) > 2:
        complete_task(sys.argv[2])
    elif cmd == "delete-task" and len(sys.argv) > 2:
        delete_task(sys.argv[2])
    elif cmd == "update-task" and len(sys.argv) > 3:
        update_task(sys.argv[2], _parse_kvs(sys.argv[3:]))
    elif cmd == "add-repeat" and len(sys.argv) > 5:
        title       = sys.argv[2]
        project     = sys.argv[3]
        cycle       = sys.argv[4]
        days        = sys.argv[5]
        start_time  = sys.argv[6] if len(sys.argv) > 6 else None
        est_min     = int(sys.argv[7]) if len(sys.argv) > 7 else 0
        add_repeat(title, project, cycle, days, start_time, est_min)
    elif cmd == "update-repeat" and len(sys.argv) > 3:
        update_repeat(sys.argv[2], _parse_kvs(sys.argv[3:]))
    elif cmd == "delete-repeat" and len(sys.argv) > 2:
        delete_repeat(sys.argv[2])
    elif cmd == "pull-push" and len(sys.argv) > 2:
        parsed = pull()
        state = parsed["state"]
        exec(sys.argv[2])
        with open(LOCAL_STATE, "w") as f:
            json.dump(parsed, f, indent=2)
        push()
    else:
        print(__doc__)
