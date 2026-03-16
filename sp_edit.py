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

    python3 sp_edit.py add-subtask "Title" "ParentTitle or ID"
        Add a subtask under a parent task.

    python3 sp_edit.py complete-subtask "Title or ID"
        Mark a subtask as done.

    python3 sp_edit.py delete-subtask "Title or ID"
        Delete a subtask and remove it from its parent.

    python3 sp_edit.py move-subtask "Title or ID" "NewParentTitle or ID"
        Move a subtask to a different parent task.

    python3 sp_edit.py tag-task "Title or ID" "TagTitle or ID"
        Add a tag to a task.

    python3 sp_edit.py untag-task "Title or ID" "TagTitle or ID"
        Remove a tag from a task.

    python3 sp_edit.py set-task-notes "Title or ID" "Markdown text"
        Set the description/notes field on a task.

    python3 sp_edit.py clear-task-notes "Title or ID"
        Clear the description/notes field on a task.

    python3 sp_edit.py move-to-backlog "Title or ID"
        Move a task to its project's backlog.

    python3 sp_edit.py move-from-backlog "Title or ID"
        Move a task from backlog back to active tasks.

    python3 sp_edit.py unschedule-task "Title or ID"
        Remove due date, TODAY tag, and planner entry from a task.

    python3 sp_edit.py reschedule-task "Title or ID" YYYY-MM-DD
        Reschedule a task to a new date (handles all side-effects).

    python3 sp_edit.py move-task-up "Title or ID"
    python3 sp_edit.py move-task-down "Title or ID"
    python3 sp_edit.py move-task-to-top "Title or ID"
    python3 sp_edit.py move-task-to-bottom "Title or ID"
        Reorder a task within its project.

    python3 sp_edit.py add-project "Title"
        Create a new project.

    python3 sp_edit.py update-project "Title or ID" field=value [field=value ...]
        Update project fields. Values are parsed as JSON (strings need quotes).
        Example: update-project "Work" title='"ZZP"'

    python3 sp_edit.py delete-project "Title or ID"
        Delete a project and all its tasks permanently.

    python3 sp_edit.py archive-project "Title or ID"
    python3 sp_edit.py unarchive-project "Title or ID"
        Archive or unarchive a project.

    python3 sp_edit.py add-tag "Title" [color]
        Create a new tag. Color is optional (e.g. '#ff0000').

    python3 sp_edit.py update-tag "Title or ID" field=value [field=value ...]
        Update tag fields.

    python3 sp_edit.py delete-tag "Title or ID"
        Delete a tag and remove it from all tasks.

    python3 sp_edit.py add-note "Title" [project] [content]
        Create a note, optionally in a project with markdown content.

    python3 sp_edit.py update-note "Title or ID" field=value [field=value ...]
        Update note fields.

    python3 sp_edit.py delete-note "Title or ID"
        Delete a note.

    python3 sp_edit.py pin-note "Title or ID"
        Pin a note to today (prepends to today's note order).

    python3 sp_edit.py unpin-note "Title or ID"
        Unpin a note from today.
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
# Phase 3a — Projects (delete, archive, unarchive)
# ---------------------------------------------------------------------------

def delete_project(title_or_id):
    parsed = pull()
    state = parsed["state"]

    project_id, project = _find_project_by_title_or_id(state, title_or_id)
    all_task_ids = project.get("taskIds", []) + project.get("backlogTaskIds", [])

    # Delete all tasks in the project
    for task_id in list(all_task_ids):
        task = state["task"]["entities"].pop(task_id, None)
        if task_id in state["task"]["ids"]:
            state["task"]["ids"].remove(task_id)
        if task:
            for tag in state["tag"]["entities"].values():
                if task_id in tag.get("taskIds", []):
                    tag["taskIds"].remove(task_id)
            for day_tasks in state["planner"]["days"].values():
                if task_id in day_tasks:
                    day_tasks.remove(task_id)

    _make_op(parsed, "DEL", "TASK", "HDM", {"taskIds": all_task_ids}, all_task_ids[0] if all_task_ids else project_id, all_task_ids or [project_id])

    # Delete the project
    del state["project"]["entities"][project_id]
    if project_id in state["project"]["ids"]:
        state["project"]["ids"].remove(project_id)

    _make_op(parsed, "DEL", "PROJECT", "PDM", {"projectId": project_id}, project_id)

    _save(parsed)
    push()
    print(f"Deleted project '{project['title']}' and {len(all_task_ids)} task(s)")


def archive_project(title_or_id):
    parsed = pull()
    state = parsed["state"]

    project_id, project = _find_project_by_title_or_id(state, title_or_id)
    project["isArchived"] = True

    _make_op(parsed, "UPD", "PROJECT", "PC", {
        "project": {"id": project_id, "changes": {"isArchived": True}},
    }, project_id)

    _save(parsed)
    push()
    print(f"Archived project '{project['title']}'")


def unarchive_project(title_or_id):
    parsed = pull()
    state = parsed["state"]

    project_id, project = _find_project_by_title_or_id(state, title_or_id)
    project["isArchived"] = False

    _make_op(parsed, "UPD", "PROJECT", "PC", {
        "project": {"id": project_id, "changes": {"isArchived": False}},
    }, project_id)

    _save(parsed)
    push()
    print(f"Unarchived project '{project['title']}'")


# ---------------------------------------------------------------------------
# Phase 3b — Tags (add, update, delete)
# ---------------------------------------------------------------------------

def add_tag(title, color=None):
    parsed = pull()
    state = parsed["state"]
    now_ms = int(time.time() * 1000)

    tag_id = _new_task_id()
    tag = {
        "id": tag_id,
        "title": title,
        "color": color,
        "created": now_ms,
        "taskIds": [],
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

    _make_op(parsed, "CRT", "TAG", "TGA", {"tag": tag}, tag_id)

    state["tag"]["entities"][tag_id] = tag
    state["tag"]["ids"].append(tag_id)

    _save(parsed)
    push()
    print(f"Created tag '{title}' (id={tag_id})")


def update_tag(title_or_id, changes):
    parsed = pull()
    state = parsed["state"]

    tag_id, tag = _find_tag_entity(state, title_or_id)

    _make_op(parsed, "UPD", "TAG", "TGU", {
        "tag": {"id": tag_id, "changes": changes},
    }, tag_id)

    tag.update(changes)

    _save(parsed)
    push()
    print(f"Updated tag '{tag['title']}': {changes}")


def delete_tag(title_or_id):
    parsed = pull()
    state = parsed["state"]

    tag_id, tag = _find_tag_entity(state, title_or_id)

    if tag_id == "TODAY":
        print("Error: cannot delete the built-in TODAY tag.")
        sys.exit(1)

    # Strip tag from all tasks
    for task in state["task"]["entities"].values():
        if tag_id in task.get("tagIds", []):
            task["tagIds"].remove(tag_id)

    del state["tag"]["entities"][tag_id]
    if tag_id in state["tag"]["ids"]:
        state["tag"]["ids"].remove(tag_id)

    _make_op(parsed, "DEL", "TAG", "TGDM", {"tagIds": [tag_id]}, tag_id)

    _save(parsed)
    push()
    print(f"Deleted tag '{tag['title']}'")


# ---------------------------------------------------------------------------
# Phase 4 — Notes
# ---------------------------------------------------------------------------

def _find_note(state, title_or_id):
    notes = state.get("note", {}).get("entities", {})
    if title_or_id in notes:
        return title_or_id, notes[title_or_id]
    needle = title_or_id.lower()
    matches = [(nid, n) for nid, n in notes.items() if n.get("title", "").lower() == needle]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Error: multiple notes match '{title_or_id}':")
        for nid, n in matches:
            print(f"  {nid}  {n['title']}")
        sys.exit(1)
    partial = [(nid, n) for nid, n in notes.items() if needle in n.get("title", "").lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        print(f"Error: multiple notes partially match '{title_or_id}':")
        for nid, n in partial:
            print(f"  {nid}  {n['title']}")
        sys.exit(1)
    print(f"Error: no note found matching '{title_or_id}'")
    sys.exit(1)


def add_note(title, project_name=None, content=""):
    parsed = pull()
    state = parsed["state"]
    now_ms = int(time.time() * 1000)

    project_id = _find_project(state, project_name) if project_name else None
    note_id = _new_task_id()

    note = {
        "id": note_id,
        "title": title,
        "content": content,
        "created": now_ms,
        "modified": now_ms,
        "projectId": project_id,
        "isPinnedToToday": False,
    }

    _make_op(parsed, "CRT", "NOTE", "NA", {"note": note}, note_id)

    state.setdefault("note", {}).setdefault("entities", {})[note_id] = note
    state["note"].setdefault("ids", []).append(note_id)

    if project_id and project_id in state["project"]["entities"]:
        state["project"]["entities"][project_id].setdefault("noteIds", []).append(note_id)

    _save(parsed)
    push()
    proj_str = f" in '{project_name}'" if project_name else ""
    print(f"Created note '{title}'{proj_str} (id={note_id})")


def update_note(title_or_id, changes):
    parsed = pull()
    state = parsed["state"]

    note_id, note = _find_note(state, title_or_id)
    changes["modified"] = int(time.time() * 1000)

    _make_op(parsed, "UPD", "NOTE", "NU", {
        "note": {"id": note_id, "changes": changes},
    }, note_id)

    note.update(changes)

    _save(parsed)
    push()
    print(f"Updated note '{note['title']}': {changes}")


def delete_note(title_or_id):
    parsed = pull()
    state = parsed["state"]

    note_id, note = _find_note(state, title_or_id)

    _make_op(parsed, "DEL", "NOTE", "NDM", {"noteIds": [note_id]}, note_id)

    del state["note"]["entities"][note_id]
    if note_id in state["note"].get("ids", []):
        state["note"]["ids"].remove(note_id)
    if note_id in state["note"].get("todayOrder", []):
        state["note"]["todayOrder"].remove(note_id)

    proj_id = note.get("projectId")
    if proj_id and proj_id in state["project"]["entities"]:
        note_ids = state["project"]["entities"][proj_id].get("noteIds", [])
        if note_id in note_ids:
            note_ids.remove(note_id)

    _save(parsed)
    push()
    print(f"Deleted note '{note['title']}'")


def pin_note(title_or_id):
    parsed = pull()
    state = parsed["state"]

    note_id, note = _find_note(state, title_or_id)
    note["isPinnedToToday"] = True
    note["modified"] = int(time.time() * 1000)

    today_order = state["note"].setdefault("todayOrder", [])
    if note_id in today_order:
        today_order.remove(note_id)
    today_order.insert(0, note_id)

    _make_op(parsed, "UPD", "NOTE", "NU", {
        "note": {"id": note_id, "changes": {"isPinnedToToday": True}},
    }, note_id)

    _save(parsed)
    push()
    print(f"Pinned note '{note['title']}' to today")


def unpin_note(title_or_id):
    parsed = pull()
    state = parsed["state"]

    note_id, note = _find_note(state, title_or_id)
    note["isPinnedToToday"] = False
    note["modified"] = int(time.time() * 1000)

    today_order = state["note"].setdefault("todayOrder", [])
    if note_id in today_order:
        today_order.remove(note_id)

    _make_op(parsed, "UPD", "NOTE", "NU", {
        "note": {"id": note_id, "changes": {"isPinnedToToday": False}},
    }, note_id)

    _save(parsed)
    push()
    print(f"Unpinned note '{note['title']}'")


# ---------------------------------------------------------------------------
# Phase 2 — Task Enhancements
# ---------------------------------------------------------------------------

def _find_tag_entity(state, title_or_id):
    tags = state["tag"]["entities"]
    if title_or_id in tags:
        return title_or_id, tags[title_or_id]
    needle = title_or_id.lower()
    matches = [(tid, t) for tid, t in tags.items() if t["title"].lower() == needle]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Error: multiple tags match '{title_or_id}':")
        for tid, t in matches:
            print(f"  {tid}  {t['title']}")
        sys.exit(1)
    print(f"Error: tag '{title_or_id}' not found.")
    print("Available:", [t["title"] for t in tags.values()])
    sys.exit(1)


def _unschedule(state, task_id, task):
    """Remove all scheduling from a task in-place (no op emitted — caller must do that)."""
    old_due = task.pop("dueDay", None)
    if "TODAY" in task.get("tagIds", []):
        task["tagIds"].remove("TODAY")
    today_tag = state["tag"]["entities"].get("TODAY")
    if today_tag and task_id in today_tag.get("taskIds", []):
        today_tag["taskIds"].remove(task_id)
    for day_tasks in state["planner"]["days"].values():
        if task_id in day_tasks:
            day_tasks.remove(task_id)
    return old_due


# 2a — Subtasks

def add_subtask(title, parent_title_or_id):
    parsed = pull()
    state = parsed["state"]
    now_ms = int(time.time() * 1000)

    parent_id, parent = _find_task(state, parent_title_or_id)
    task_id = _new_task_id()

    task = {
        "id": task_id,
        "parentId": parent_id,
        "subTaskIds": [],
        "timeSpentOnDay": {},
        "timeSpent": 0,
        "timeEstimate": 0,
        "isDone": False,
        "title": title,
        "tagIds": [],
        "created": now_ms,
        "attachments": [],
        "projectId": parent.get("projectId"),
    }

    _make_op(parsed, "CRT", "TASK", "HA", {
        "task": task,
        "workContextId": parent_id,
        "workContextType": "TASK",
        "isAddToBacklog": False,
        "isAddToBottom": True,
    }, task_id)

    state["task"]["entities"][task_id] = task
    state["task"]["ids"].append(task_id)
    parent.setdefault("subTaskIds", []).append(task_id)

    _save(parsed)
    push()
    print(f"Added subtask '{title}' under '{parent['title']}'")


def complete_subtask(title_or_id):
    complete_task(title_or_id)


def delete_subtask(title_or_id):
    parsed = pull()
    state = parsed["state"]

    task_id, task = _find_task(state, title_or_id)
    parent_id = task.get("parentId")

    _make_op(parsed, "DEL", "TASK", "HDM", {"taskIds": [task_id]}, task_id)

    del state["task"]["entities"][task_id]
    if task_id in state["task"]["ids"]:
        state["task"]["ids"].remove(task_id)
    if parent_id and parent_id in state["task"]["entities"]:
        parent = state["task"]["entities"][parent_id]
        if task_id in parent.get("subTaskIds", []):
            parent["subTaskIds"].remove(task_id)

    _save(parsed)
    push()
    print(f"Deleted subtask '{task['title']}'")


def move_subtask(title_or_id, new_parent_title_or_id):
    parsed = pull()
    state = parsed["state"]

    task_id, task = _find_task(state, title_or_id)
    new_parent_id, new_parent = _find_task(state, new_parent_title_or_id)

    old_parent_id = task.get("parentId")
    if old_parent_id and old_parent_id in state["task"]["entities"]:
        old_parent = state["task"]["entities"][old_parent_id]
        if task_id in old_parent.get("subTaskIds", []):
            old_parent["subTaskIds"].remove(task_id)

    task["parentId"] = new_parent_id
    task["projectId"] = new_parent.get("projectId")
    new_parent.setdefault("subTaskIds", []).append(task_id)

    _make_op(parsed, "UPD", "TASK", "HU", {
        "task": {"id": task_id, "changes": {"parentId": new_parent_id, "projectId": task["projectId"]}},
    }, task_id)

    _save(parsed)
    push()
    print(f"Moved subtask '{task['title']}' to '{new_parent['title']}'")


# 2b — Task Tagging

def tag_task(title_or_id, tag_title_or_id):
    parsed = pull()
    state = parsed["state"]

    task_id, task = _find_task(state, title_or_id)
    tag_id, tag = _find_tag_entity(state, tag_title_or_id)

    if tag_id in task.get("tagIds", []):
        print(f"Task '{task['title']}' already has tag '{tag['title']}'")
        return

    task.setdefault("tagIds", []).append(tag_id)
    tag.setdefault("taskIds", []).append(task_id)

    # Handle TODAY scheduling side-effects
    if tag_id == "TODAY":
        today = str(date.today())
        task["dueDay"] = task.get("dueDay") or today
        state["planner"]["days"].setdefault(task["dueDay"], [])
        if task_id not in state["planner"]["days"][task["dueDay"]]:
            state["planner"]["days"][task["dueDay"]].append(task_id)

    _make_op(parsed, "UPD", "TASK", "HU", {
        "task": {"id": task_id, "changes": {"tagIds": task["tagIds"]}},
    }, task_id)

    _save(parsed)
    push()
    print(f"Tagged '{task['title']}' with '{tag['title']}'")


def untag_task(title_or_id, tag_title_or_id):
    parsed = pull()
    state = parsed["state"]

    task_id, task = _find_task(state, title_or_id)
    tag_id, tag = _find_tag_entity(state, tag_title_or_id)

    if tag_id not in task.get("tagIds", []):
        print(f"Task '{task['title']}' does not have tag '{tag['title']}'")
        return

    task["tagIds"].remove(tag_id)
    if task_id in tag.get("taskIds", []):
        tag["taskIds"].remove(task_id)

    changes = {"tagIds": task["tagIds"]}

    # If removing TODAY, also clean up dueDay and planner
    if tag_id == "TODAY":
        _unschedule(state, task_id, task)
        changes = {"tagIds": task["tagIds"], "dueDay": None}

    _make_op(parsed, "UPD", "TASK", "HU", {
        "task": {"id": task_id, "changes": changes},
    }, task_id)

    _save(parsed)
    push()
    print(f"Removed tag '{tag['title']}' from '{task['title']}'")


# 2c — Task Description

def set_task_notes(title_or_id, notes_text):
    parsed = pull()
    state = parsed["state"]

    task_id, task = _find_task(state, title_or_id)
    task["notes"] = notes_text

    _make_op(parsed, "UPD", "TASK", "HU", {
        "task": {"id": task_id, "changes": {"notes": notes_text}},
    }, task_id)

    _save(parsed)
    push()
    print(f"Set notes on '{task['title']}'")


def clear_task_notes(title_or_id):
    set_task_notes(title_or_id, "")


# 2d — Backlog Management

def move_to_backlog(title_or_id):
    parsed = pull()
    state = parsed["state"]

    task_id, task = _find_task(state, title_or_id)
    proj_id = task.get("projectId")
    if not proj_id or proj_id not in state["project"]["entities"]:
        print(f"Error: task '{task['title']}' has no project and cannot be moved to backlog.")
        sys.exit(1)

    project = state["project"]["entities"][proj_id]
    if task_id in project.get("taskIds", []):
        project["taskIds"].remove(task_id)
    if task_id not in project.get("backlogTaskIds", []):
        project.setdefault("backlogTaskIds", []).append(task_id)

    _make_op(parsed, "UPD", "TASK", "HU", {
        "task": {"id": task_id, "changes": {}},
    }, task_id)

    _save(parsed)
    push()
    print(f"Moved '{task['title']}' to backlog of '{project['title']}'")


def move_from_backlog(title_or_id):
    parsed = pull()
    state = parsed["state"]

    task_id, task = _find_task(state, title_or_id)
    proj_id = task.get("projectId")
    if not proj_id or proj_id not in state["project"]["entities"]:
        print(f"Error: task '{task['title']}' has no project.")
        sys.exit(1)

    project = state["project"]["entities"][proj_id]
    if task_id in project.get("backlogTaskIds", []):
        project["backlogTaskIds"].remove(task_id)
    if task_id not in project.get("taskIds", []):
        project.setdefault("taskIds", []).append(task_id)

    _make_op(parsed, "UPD", "TASK", "HU", {
        "task": {"id": task_id, "changes": {}},
    }, task_id)

    _save(parsed)
    push()
    print(f"Moved '{task['title']}' from backlog to active tasks in '{project['title']}'")


# 2e — Scheduling

def unschedule_task(title_or_id):
    parsed = pull()
    state = parsed["state"]

    task_id, task = _find_task(state, title_or_id)
    _unschedule(state, task_id, task)

    _make_op(parsed, "UPD", "TASK", "HU", {
        "task": {"id": task_id, "changes": {"dueDay": None, "tagIds": task.get("tagIds", [])}},
    }, task_id)

    _save(parsed)
    push()
    print(f"Unscheduled '{task['title']}'")


def reschedule_task(title_or_id, new_date):
    parsed = pull()
    state = parsed["state"]

    task_id, task = _find_task(state, title_or_id)

    # Remove old scheduling
    _unschedule(state, task_id, task)

    # Apply new date
    task["dueDay"] = new_date
    today = str(date.today())
    if new_date == today:
        if "TODAY" not in task.get("tagIds", []):
            task.setdefault("tagIds", []).append("TODAY")
        today_tag = state["tag"]["entities"].get("TODAY")
        if today_tag and task_id not in today_tag.get("taskIds", []):
            today_tag.setdefault("taskIds", []).append(task_id)

    state["planner"]["days"].setdefault(new_date, [])
    if task_id not in state["planner"]["days"][new_date]:
        state["planner"]["days"][new_date].append(task_id)

    _make_op(parsed, "UPD", "TASK", "HU", {
        "task": {"id": task_id, "changes": {"dueDay": new_date, "tagIds": task.get("tagIds", [])}},
    }, task_id)

    _save(parsed)
    push()
    print(f"Rescheduled '{task['title']}' to {new_date}")


# 2f — Task Ordering

def _reorder_task(title_or_id, delta=None, to_index=None):
    """Move a task within its project's taskIds list."""
    parsed = pull()
    state = parsed["state"]

    task_id, task = _find_task(state, title_or_id)
    proj_id = task.get("projectId")
    if not proj_id or proj_id not in state["project"]["entities"]:
        print(f"Error: task '{task['title']}' has no project.")
        sys.exit(1)

    task_ids = state["project"]["entities"][proj_id]["taskIds"]
    if task_id not in task_ids:
        print(f"Error: task '{task['title']}' is not in the active task list (may be in backlog).")
        sys.exit(1)

    idx = task_ids.index(task_id)
    task_ids.remove(task_id)

    if to_index is not None:
        new_idx = to_index if to_index >= 0 else len(task_ids)
    else:
        new_idx = max(0, min(len(task_ids), idx + delta))

    task_ids.insert(new_idx, task_id)

    _make_op(parsed, "UPD", "TASK", "HU", {
        "task": {"id": task_id, "changes": {}},
    }, task_id)

    _save(parsed)
    push()
    return task["title"]


def move_task_up(title_or_id):
    title = _reorder_task(title_or_id, delta=-1)
    print(f"Moved '{title}' up")


def move_task_down(title_or_id):
    title = _reorder_task(title_or_id, delta=1)
    print(f"Moved '{title}' down")


def move_task_to_top(title_or_id):
    title = _reorder_task(title_or_id, to_index=0)
    print(f"Moved '{title}' to top")


def move_task_to_bottom(title_or_id):
    title = _reorder_task(title_or_id, to_index=-1)
    print(f"Moved '{title}' to bottom")


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
    elif cmd == "add-subtask" and len(args) > 2:
        add_subtask(args[1], args[2])
    elif cmd == "complete-subtask" and len(args) > 1:
        complete_subtask(args[1])
    elif cmd == "delete-subtask" and len(args) > 1:
        delete_subtask(args[1])
    elif cmd == "move-subtask" and len(args) > 2:
        move_subtask(args[1], args[2])
    elif cmd == "tag-task" and len(args) > 2:
        tag_task(args[1], args[2])
    elif cmd == "untag-task" and len(args) > 2:
        untag_task(args[1], args[2])
    elif cmd == "set-task-notes" and len(args) > 2:
        set_task_notes(args[1], args[2])
    elif cmd == "clear-task-notes" and len(args) > 1:
        clear_task_notes(args[1])
    elif cmd == "move-to-backlog" and len(args) > 1:
        move_to_backlog(args[1])
    elif cmd == "move-from-backlog" and len(args) > 1:
        move_from_backlog(args[1])
    elif cmd == "unschedule-task" and len(args) > 1:
        unschedule_task(args[1])
    elif cmd == "reschedule-task" and len(args) > 2:
        reschedule_task(args[1], args[2])
    elif cmd == "move-task-up" and len(args) > 1:
        move_task_up(args[1])
    elif cmd == "move-task-down" and len(args) > 1:
        move_task_down(args[1])
    elif cmd == "move-task-to-top" and len(args) > 1:
        move_task_to_top(args[1])
    elif cmd == "move-task-to-bottom" and len(args) > 1:
        move_task_to_bottom(args[1])
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
    elif cmd == "delete-project" and len(args) > 1:
        delete_project(args[1])
    elif cmd == "archive-project" and len(args) > 1:
        archive_project(args[1])
    elif cmd == "unarchive-project" and len(args) > 1:
        unarchive_project(args[1])
    elif cmd == "add-tag" and len(args) > 1:
        add_tag(args[1], args[2] if len(args) > 2 else None)
    elif cmd == "update-tag" and len(args) > 2:
        update_tag(args[1], _parse_kvs(args[2:]))
    elif cmd == "delete-tag" and len(args) > 1:
        delete_tag(args[1])
    elif cmd == "add-note" and len(args) > 1:
        add_note(args[1], args[2] if len(args) > 2 else None, args[3] if len(args) > 3 else "")
    elif cmd == "update-note" and len(args) > 2:
        update_note(args[1], _parse_kvs(args[2:]))
    elif cmd == "delete-note" and len(args) > 1:
        delete_note(args[1])
    elif cmd == "pin-note" and len(args) > 1:
        pin_note(args[1])
    elif cmd == "unpin-note" and len(args) > 1:
        unpin_note(args[1])
    elif cmd == "pull-push" and len(args) > 1:
        parsed = pull()
        state = parsed["state"]
        exec(args[1])
        with open(LOCAL_STATE, "w") as f:
            json.dump(parsed, f, indent=2)
        push()
    else:
        print(__doc__)
