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

    python3 sp_edit.py dump-today
        List tasks scheduled for today (dueDay=today or TODAY tag), sorted by project.

    python3 sp_edit.py dump-projects
        List all projects with task and backlog counts.

    python3 sp_edit.py dump-tags
        List all tags with task counts.

    python3 sp_edit.py dump-project "Title or ID"
        List tasks in a specific project.

    python3 sp_edit.py dump-tag "Title"
        List tasks carrying a specific tag.

    python3 sp_edit.py dump-backlog "Title or ID"
        List backlog tasks for a specific project.

    python3 sp_edit.py dump-notes
        List all notes (title, project, pinned status).

    python3 sp_edit.py dump-counters
        List all simple counters with today's value.

    python3 sp_edit.py dump-archive
        List archived tasks (archiveYoung + archiveOld).

All dump-* commands accept --json for machine-readable output.

    python3 sp_edit.py add-project "Title"
        Create a new project.

    python3 sp_edit.py update-project "Title or ID" field=value [field=value ...]
        Update project fields. Values are parsed as JSON (strings need quotes).
        Example: update-project "Work" title='"ZZP"'
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


def _find_project_by_title_or_id(state, title_or_id):
    projects = state["project"]["entities"]
    if title_or_id in projects:
        return title_or_id, projects[title_or_id]
    needle = title_or_id.lower()
    matches = [(pid, p) for pid, p in projects.items() if p["title"].lower() == needle]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Error: multiple projects match '{title_or_id}':")
        for pid, p in matches:
            print(f"  {pid}  {p['title']}")
        sys.exit(1)
    print(f"Error: no project found matching '{title_or_id}'")
    print("Available:", [p["title"] for p in projects.values()])
    sys.exit(1)


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

def _load_state():
    pull()
    with open(LOCAL_STATE) as f:
        return json.load(f)


def _print_or_json(rows, json_out):
    if json_out:
        print(json.dumps(rows, indent=2, ensure_ascii=False))


def dump(json_out=False):
    parsed = _load_state()
    tasks = parsed["state"]["task"]["entities"]
    projects = {p["id"]: p["title"] for p in parsed["state"]["project"]["entities"].values()}
    tags = {t["id"]: t["title"] for t in parsed["state"]["tag"]["entities"].values()}
    rows = []
    for tid, t in tasks.items():
        proj = projects.get(t.get("projectId"), "")
        tag_names = [tags.get(x, x) for x in t.get("tagIds", [])]
        if json_out:
            rows.append({"id": tid, "title": t["title"], "project": proj,
                         "tags": tag_names, "done": t.get("isDone", False)})
        else:
            done = "✓" if t.get("isDone") else " "
            print(f"[{done}] {t['title']:<50} project={proj}  tags={tag_names}  id={tid}")
    _print_or_json(rows, json_out)


def dump_repeats(json_out=False):
    parsed = _load_state()
    cfgs = parsed["state"]["taskRepeatCfg"]["entities"]
    projects = {p["id"]: p["title"] for p in parsed["state"]["project"]["entities"].values()}
    rows = []
    for rid, r in cfgs.items():
        proj = projects.get(r.get("projectId"), "")
        days = [d[:3] for d in DAY_FIELDS if r.get(d)]
        if json_out:
            rows.append({"id": rid, "title": r["title"], "project": proj,
                         "cycle": r.get("repeatCycle"), "days": days,
                         "startTime": r.get("startTime"), "isPaused": r.get("isPaused", False),
                         "defaultEstimate": r.get("defaultEstimate", 0)})
        else:
            time_str = f" @{r['startTime']}" if r.get("startTime") else ""
            est = r.get("defaultEstimate", 0)
            est_str = f" est={est // 60000}m" if est else ""
            paused = " [PAUSED]" if r.get("isPaused") else ""
            print(f"{r['title']:<45} {r.get('repeatCycle','?'):<8} {','.join(days):<25} project={proj}{time_str}{est_str}{paused}  id={rid}")
    _print_or_json(rows, json_out)


def dump_today(json_out=False):
    parsed = _load_state()
    state = parsed["state"]
    tasks = state["task"]["entities"]
    projects = {p["id"]: p["title"] for p in state["project"]["entities"].values()}
    today = str(date.today())

    today_tasks = [
        t for t in tasks.values()
        if t.get("dueDay") == today or "TODAY" in t.get("tagIds", [])
    ]
    today_tasks.sort(key=lambda t: (projects.get(t.get("projectId"), ""), t["title"]))

    if not today_tasks:
        if not json_out:
            print("No tasks scheduled for today.")
        else:
            print("[]")
        return

    rows = []
    total_est = 0
    total_spent = 0
    for t in today_tasks:
        proj = projects.get(t.get("projectId"), "")
        est_ms = t.get("timeEstimate", 0) or 0
        spent_ms = t.get("timeSpent", 0) or 0
        total_est += est_ms
        total_spent += spent_ms
        if json_out:
            rows.append({"id": t["id"], "title": t["title"], "project": proj,
                         "done": t.get("isDone", False), "dueDay": t.get("dueDay"),
                         "timeEstimate": est_ms, "timeSpent": spent_ms})
        else:
            done = "✓" if t.get("isDone") else " "
            est_str = f"{est_ms // 60000}m" if est_ms else "   -"
            spent_str = f"{spent_ms // 60000}m" if spent_ms else "  -"
            print(f"[{done}] {t['title']:<50} project={proj:<20} est={est_str:<5} spent={spent_str}")

    if json_out:
        _print_or_json(rows, json_out)
    else:
        print(f"\n{'':>4} {len(today_tasks)} tasks — est total: {total_est // 60000}m  spent total: {total_spent // 60000}m")


def dump_projects(json_out=False):
    parsed = _load_state()
    projects = parsed["state"]["project"]["entities"]
    rows = []
    for p in projects.values():
        task_count = len(p.get("taskIds", []))
        backlog_count = len(p.get("backlogTaskIds", []))
        if json_out:
            rows.append({"id": p["id"], "title": p["title"], "tasks": task_count,
                         "backlog": backlog_count, "isArchived": p.get("isArchived", False)})
        else:
            archived = " [archived]" if p.get("isArchived") else ""
            print(f"{p['title']:<40} tasks={task_count:<4} backlog={backlog_count}{archived}  id={p['id']}")
    _print_or_json(rows, json_out)


def dump_tags(json_out=False):
    parsed = _load_state()
    tags = parsed["state"]["tag"]["entities"]
    rows = []
    for t in tags.values():
        task_count = len(t.get("taskIds", []))
        if json_out:
            rows.append({"id": t["id"], "title": t["title"], "tasks": task_count})
        else:
            print(f"{t['title']:<30} tasks={task_count:<4}  id={t['id']}")
    _print_or_json(rows, json_out)


def dump_project(project_name, json_out=False):
    parsed = _load_state()
    state = parsed["state"]
    project_id, project = _find_project_by_title_or_id(state, project_name)
    tasks = state["task"]["entities"]
    tags = {t["id"]: t["title"] for t in state["tag"]["entities"].values()}

    task_ids = project.get("taskIds", [])
    if not task_ids:
        if not json_out:
            print(f"No tasks in '{project['title']}'.")
        else:
            print("[]")
        return
    rows = []
    for tid in task_ids:
        t = tasks.get(tid)
        if not t:
            continue
        tag_names = [tags.get(x, x) for x in t.get("tagIds", []) if x != "TODAY"]
        if json_out:
            rows.append({"id": tid, "title": t["title"], "done": t.get("isDone", False),
                         "dueDay": t.get("dueDay"), "tags": tag_names})
        else:
            done = "✓" if t.get("isDone") else " "
            due = f"  due={t['dueDay']}" if t.get("dueDay") else ""
            tags_str = f"  tags={tag_names}" if tag_names else ""
            print(f"[{done}] {t['title']:<50}{due}{tags_str}  id={tid}")
    _print_or_json(rows, json_out)


def dump_tag(tag_name, json_out=False):
    parsed = _load_state()
    state = parsed["state"]
    tags = state["tag"]["entities"]

    tag = next((t for t in tags.values() if t["title"].lower() == tag_name.lower()), None)
    if tag is None:
        print(f"Error: tag '{tag_name}' not found.")
        print("Available:", [t["title"] for t in tags.values()])
        sys.exit(1)

    task_entities = state["task"]["entities"]
    projects = {p["id"]: p["title"] for p in state["project"]["entities"].values()}
    rows = []
    for tid in tag.get("taskIds", []):
        t = task_entities.get(tid)
        if not t:
            continue
        proj = projects.get(t.get("projectId"), "")
        if json_out:
            rows.append({"id": tid, "title": t["title"], "project": proj,
                         "done": t.get("isDone", False), "dueDay": t.get("dueDay")})
        else:
            done = "✓" if t.get("isDone") else " "
            due = f"  due={t['dueDay']}" if t.get("dueDay") else ""
            print(f"[{done}] {t['title']:<50} project={proj}{due}  id={tid}")
    _print_or_json(rows, json_out)


def dump_backlog(project_name, json_out=False):
    parsed = _load_state()
    state = parsed["state"]
    project_id, project = _find_project_by_title_or_id(state, project_name)
    tasks = state["task"]["entities"]

    backlog_ids = project.get("backlogTaskIds", [])
    if not backlog_ids:
        if not json_out:
            print(f"No backlog tasks in '{project['title']}'.")
        else:
            print("[]")
        return
    rows = []
    for tid in backlog_ids:
        t = tasks.get(tid)
        if not t:
            continue
        est_ms = t.get("timeEstimate", 0) or 0
        if json_out:
            rows.append({"id": tid, "title": t["title"], "done": t.get("isDone", False),
                         "timeEstimate": est_ms})
        else:
            done = "✓" if t.get("isDone") else " "
            est_str = f"  est={est_ms // 60000}m" if est_ms else ""
            print(f"[{done}] {t['title']:<50}{est_str}  id={tid}")
    _print_or_json(rows, json_out)


def dump_notes(json_out=False):
    parsed = _load_state()
    state = parsed["state"]
    notes = state.get("note", {}).get("entities", {})
    today_order = state.get("note", {}).get("todayOrder", [])
    projects = {p["id"]: p["title"] for p in state["project"]["entities"].values()}

    if not notes:
        if not json_out:
            print("No notes found.")
        else:
            print("[]")
        return
    rows = []
    for nid, n in notes.items():
        proj = projects.get(n.get("projectId"), "")
        pinned = n.get("isPinnedToToday", False)
        if json_out:
            rows.append({"id": nid, "title": n.get("title", ""), "project": proj,
                         "pinned": pinned})
        else:
            pin_str = " [pinned]" if pinned else ""
            print(f"{n.get('title', ''):<50} project={proj}{pin_str}  id={nid}")
    _print_or_json(rows, json_out)


def dump_counters(json_out=False):
    parsed = _load_state()
    state = parsed["state"]
    counters = state.get("simpleCounter", {}).get("entities", {})
    today = str(date.today())

    if not counters:
        if not json_out:
            print("No counters found.")
        else:
            print("[]")
        return
    rows = []
    sorted_counters = sorted(counters.values(), key=lambda c: c.get("order", 0))
    for c in sorted_counters:
        today_val = c.get("countOnDay", {}).get(today, 0)
        if json_out:
            rows.append({"id": c["id"], "title": c["title"], "type": c.get("type"),
                         "todayValue": today_val, "countOnDay": c.get("countOnDay", {})})
        else:
            print(f"{c['title']:<40} type={c.get('type','?'):<8} today={today_val}  id={c['id']}")
    _print_or_json(rows, json_out)


def dump_archive(json_out=False):
    parsed = _load_state()
    state = parsed["state"]
    projects = {p["id"]: p["title"] for p in state["project"]["entities"].values()}

    rows = []
    for archive_key in ("archiveYoung", "archiveOld"):
        archive = state.get(archive_key, {})
        tasks = archive.get("task", {}).get("entities", {})
        for tid, t in tasks.items():
            proj = projects.get(t.get("projectId"), "")
            if json_out:
                rows.append({"id": tid, "title": t["title"], "project": proj,
                             "archive": archive_key, "dueDay": t.get("dueDay")})
            else:
                due = f"  due={t['dueDay']}" if t.get("dueDay") else ""
                print(f"{t['title']:<50} project={proj}{due}  [{archive_key}]  id={tid}")

    if not rows and json_out:
        print("[]")
    elif not rows:
        print("No archived tasks found.")
    elif json_out:
        _print_or_json(rows, json_out)


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


def add_project(title):
    parsed = pull()
    state = parsed["state"]

    project_id = _new_task_id()
    project = {
        "id": project_id,
        "title": title,
        "isHiddenFromMenu": False,
        "isArchived": False,
        "isEnableBacklog": True,
        "taskIds": [],
        "backlogTaskIds": [],
        "noteIds": [],
        "icon": None,
        "theme": {
            "isAutoContrast": True,
            "isDisableBackgroundTint": False,
            "primary": "#29a1aa",
            "huePrimary": "500",
            "accent": "#ff4081",
            "hueAccent": "500",
            "warn": "#e11826",
            "hueWarn": "500",
            "backgroundImageDark": None,
            "backgroundImageLight": None,
            "backgroundOverlayOpacity": 20,
        },
        "advancedCfg": {
            "worklogExportSettings": {
                "cols": ["DATE", "START", "END", "TIME_CLOCK", "TITLES_INCLUDING_SUB"],
                "roundWorkTimeTo": None,
                "roundStartTimeTo": None,
                "roundEndTimeTo": None,
                "separateTasksBy": " | ",
                "groupBy": "DATE",
            }
        },
    }

    _make_op(parsed, "CRT", "PROJECT", "PA", {"project": project}, project_id)

    state["project"]["entities"][project_id] = project
    state["project"]["ids"].append(project_id)

    _save(parsed)
    push()
    print(f"Created project '{title}' (id={project_id})")


def update_project(title_or_id, changes):
    parsed = pull()
    state = parsed["state"]

    project_id, project = _find_project_by_title_or_id(state, title_or_id)

    _make_op(parsed, "UPD", "PROJECT", "PC", {
        "project": {"id": project_id, "changes": changes},
    }, project_id)

    project.update(changes)

    _save(parsed)
    push()
    print(f"Updated project '{project['title']}': {changes}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--json"]
    json_out = "--json" in sys.argv
    cmd = args[0] if args else "dump"

    if cmd == "pull":
        pull()
    elif cmd == "push":
        push()
    elif cmd == "dump":
        dump(json_out)
    elif cmd == "dump-repeats":
        dump_repeats(json_out)
    elif cmd == "dump-today":
        dump_today(json_out)
    elif cmd == "dump-projects":
        dump_projects(json_out)
    elif cmd == "dump-tags":
        dump_tags(json_out)
    elif cmd == "dump-project" and len(args) > 1:
        dump_project(args[1], json_out)
    elif cmd == "dump-tag" and len(args) > 1:
        dump_tag(args[1], json_out)
    elif cmd == "dump-backlog" and len(args) > 1:
        dump_backlog(args[1], json_out)
    elif cmd == "dump-notes":
        dump_notes(json_out)
    elif cmd == "dump-counters":
        dump_counters(json_out)
    elif cmd == "dump-archive":
        dump_archive(json_out)
    elif cmd == "add-task" and len(args) > 1:
        title    = args[1]
        project  = args[2] if len(args) > 2 else "Inbox"
        raw_date = args[3] if len(args) > 3 else str(date.today())
        due      = None if raw_date.lower() == "none" else raw_date
        add_task(title, project, due)
    elif cmd == "complete-task" and len(args) > 1:
        complete_task(args[1])
    elif cmd == "delete-task" and len(args) > 1:
        delete_task(args[1])
    elif cmd == "update-task" and len(args) > 2:
        update_task(args[1], _parse_kvs(args[2:]))
    elif cmd == "add-repeat" and len(args) > 4:
        title       = args[1]
        project     = args[2]
        cycle       = args[3]
        days        = args[4]
        start_time  = args[5] if len(args) > 5 else None
        est_min     = int(args[6]) if len(args) > 6 else 0
        add_repeat(title, project, cycle, days, start_time, est_min)
    elif cmd == "update-repeat" and len(args) > 2:
        update_repeat(args[1], _parse_kvs(args[2:]))
    elif cmd == "delete-repeat" and len(args) > 1:
        delete_repeat(args[1])
    elif cmd == "add-project" and len(args) > 1:
        add_project(args[1])
    elif cmd == "update-project" and len(args) > 2:
        update_project(args[1], _parse_kvs(args[2:]))
    elif cmd == "pull-push" and len(args) > 1:
        parsed = pull()
        state = parsed["state"]
        exec(args[1])
        with open(LOCAL_STATE, "w") as f:
            json.dump(parsed, f, indent=2)
        push()
    else:
        print(__doc__)
