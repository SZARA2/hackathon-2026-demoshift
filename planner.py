"""Small exact, discrete working-time planner for a synthetic robotics PoC.

One slot is four working hours. The solver enumerates serial schedules over
every topological priority order, allocates exclusive resources, and selects
the shortest schedule. It checks only the constraints declared in this model.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

SLOT_HOURS = 4
SLOTS_PER_DAY = 2
SCHEMA_VERSION = 1
PEOPLE = {
    "solution": "Maya · Solutions lead",
    "mechanical": "Leon · Cell engineer",
    "software": "Jules · Integration engineer",
}
CAMERAS = {
    "contracted_3d": {"name": "DepthPro 3D · contracted", "interface": "GigE", "features": ["pose_3d", "barcode"], "ready_day": 0},
    "rental_3d": {"name": "Scout 3D · rental", "interface": "USB3", "features": ["pose_3d", "barcode"], "ready_day": 1},
    "bench_2d": {"name": "BenchCam 2D · existing", "interface": "GigE", "features": ["pose_2d", "barcode"], "ready_day": 0},
}
DEFAULT = {
    "customer": "Northstar Components",
    "goal": "Demonstrate 3D part localization, barcode traceability and a supervised pick-and-place handover.",
    "demo_day": 7,
    "camera_delay_days": 0,
    "primary_unavailable": False,
    "adapter_available": True,
    "engineer_start_day": 0,
    "part_weight_kg": 2.0,
    "requires_3d": True,
    "recovery_budget_usd": 1500,
}


class PlanError(ValueError):
    pass


def validate_request(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise PlanError("A JSON object is required.")
    unknown = set(raw) - set(DEFAULT)
    if unknown:
        raise PlanError("Unknown fields: " + ", ".join(sorted(unknown)))
    cfg = {**DEFAULT, **raw}
    for key in ("customer", "goal"):
        if not isinstance(cfg[key], str) or not cfg[key].strip() or len(cfg[key]) > (100 if key == "customer" else 1000):
            raise PlanError(f"{key} must be non-empty text within its length limit.")
        cfg[key] = cfg[key].strip()
    for key, lower, upper in (("demo_day", 3, 25), ("camera_delay_days", 0, 20), ("engineer_start_day", 0, 20), ("recovery_budget_usd", 0, 20000)):
        if type(cfg[key]) is not int or not lower <= cfg[key] <= upper:
            raise PlanError(f"{key} must be an integer from {lower} to {upper}.")
    for key in ("primary_unavailable", "adapter_available", "requires_3d"):
        if type(cfg[key]) is not bool:
            raise PlanError(f"{key} must be true or false.")
    weight = cfg["part_weight_kg"]
    if type(weight) not in (int, float) or not math.isfinite(weight) or not 0.1 <= weight <= 20:
        raise PlanError("part_weight_kg must be a finite number from 0.1 to 20.")
    cfg["part_weight_kg"] = float(weight)
    return cfg


@dataclass(frozen=True)
class Task:
    id: str
    label: str
    slots: int
    resources: tuple[str, ...]
    deps: tuple[str, ...] = ()
    release: int = 0
    equipment: tuple[str, ...] = ()
    output: str = ""


def solve(tasks: list[Task], resource_ready: dict[str, int] | None = None) -> dict:
    """Find a minimum-makespan serial schedule; inputs are small and synthetic.

    All topological priority lists are considered. Earliest insertion permits
    parallel work and respects task releases plus each named resource's start.
    No global optimality claim is made outside this discrete, fixed-task model.
    """
    resource_ready = resource_ready or {}
    by_id = {task.id: task for task in tasks}
    if len(by_id) != len(tasks) or any(task.slots < 1 or not task.resources or any(dep not in by_id for dep in task.deps) for task in tasks):
        raise PlanError("Invalid task graph.")
    best = None
    explored = 0

    def visit(scheduled: dict, occupied: dict[str, set[int]]):
        nonlocal best, explored
        if len(scheduled) == len(tasks):
            explored += 1
            end = max((entry["end_slot"] for entry in scheduled.values()), default=0)
            # Deterministic tie-breaking makes reports and replays stable.
            candidate_key = (end, tuple((scheduled[t.id]["start_slot"], t.id) for t in tasks))
            if best is None or candidate_key < best[0]:
                best = (candidate_key, {key: value.copy() for key, value in scheduled.items()})
            return
        ready = [task for task in tasks if task.id not in scheduled and all(dep in scheduled for dep in task.deps)]
        if not ready:
            raise PlanError("Task dependencies contain a cycle.")
        for task in ready:
            start = max([task.release] + [resource_ready.get(r, 0) for r in task.resources] + [scheduled[d]["end_slot"] for d in task.deps])
            while any(slot in occupied.get(r, set()) for r in task.resources for slot in range(start, start + task.slots)):
                start += 1
            end = start + task.slots
            if best and end > best[0][0]:
                continue
            next_occupied = {r: set(slots) for r, slots in occupied.items()}
            for resource in task.resources:
                next_occupied.setdefault(resource, set()).update(range(start, end))
            scheduled[task.id] = {"id": task.id, "label": task.label, "start_slot": start, "end_slot": end,
                                  "hours": task.slots * SLOT_HOURS, "resources": list(task.resources), "depends_on": list(task.deps),
                                  "equipment": list(task.equipment), "output": task.output}
            visit(scheduled, next_occupied)
            scheduled.pop(task.id)

    visit({}, {})
    if best is None:
        raise PlanError("No schedule found.")
    return {"finish_slot": best[0][0], "finish_day": best[0][0] / SLOTS_PER_DAY,
            "tasks": sorted(best[1].values(), key=lambda row: (row["start_slot"], row["id"])), "schedules_evaluated": explored}


def build_tasks(camera: str, ready_day: int, reduced: bool) -> list[Task]:
    mount_release = ready_day * SLOTS_PER_DAY
    tasks = [
        Task("scope", "Confirm customer success criteria", 1, ("solution",), output="Versioned acceptance checklist"),
        Task("layout", "Prepare cell layout and fixture", 2, ("mechanical",), ("scope",), equipment=("arm", "gripper"), output="Cell layout and fixture checklist"),
        Task("program", "Build robot sequence with simulated poses", 3, ("software",), ("scope",), equipment=("arm", "gripper"), output="Supervised robot sequence; poses still simulated"),
        Task("mount", "Mount and connect vision equipment", 1, ("mechanical",), ("layout",), mount_release, ("arm", "gripper", camera), "Mounted camera and recorded I/O check"),
    ]
    vision_dep = "mount"
    if camera == "rental_3d":
        tasks.append(Task("adapter", "Configure USB3 gateway and driver", 1, ("software",), ("mount",), equipment=("usb3_gateway", camera), output="Gateway communication check"))
        vision_dep = "adapter"
    tasks += [
        Task("vision", "Calibrate " + ("2D barcode and guided pose" if reduced else "3D pose and barcode"), 1 if reduced else 2,
             ("software",), (vision_dep,), equipment=(camera,), output="Calibration evidence and example detections"),
        Task("safety", "Review supervised operating procedure", 1, ("mechanical", "solution"), ("mount",), equipment=("arm",), output="Human-reviewed safety checklist; not certification"),
        Task("integrate", "Integrate perception and robot handoff", 2, ("software",), ("program", "vision"), equipment=("arm", camera), output="Integrated demonstration candidate"),
        Task("rehearse", "Rehearse customer scenario", 1, ("software", "solution"), ("integrate", "safety"), output="Recorded rehearsal and exception checklist"),
        Task("handover", "Prepare customer evidence pack", 1, ("solution",), ("rehearse",), output="BOM, WBS, runbook and acceptance evidence index"),
    ]
    return tasks


def _bom(camera: str) -> list[dict]:
    rows = [
        {"id": "arm", "item": "Atlas A6 collaborative arm", "quantity": 1, "status": "Existing synthetic asset", "constraint": "6 kg declared payload; GigE controller"},
        {"id": "gripper", "item": "Pinch G5 electric gripper", "quantity": 1, "status": "Existing synthetic asset", "constraint": "5 kg declared workpiece limit"},
        {"id": camera, "item": CAMERAS[camera]["name"], "quantity": 1, "status": "Rental proposal" if camera == "rental_3d" else "Declared inventory", "constraint": CAMERAS[camera]["interface"] + " · " + ", ".join(CAMERAS[camera]["features"])},
    ]
    if camera == "rental_3d":
        rows.append({"id": "usb3_gateway", "item": "USB3-to-controller gateway", "quantity": 1, "status": "Additional procurement proposal", "constraint": "Required for the selected camera interface"})
    return rows


def evaluate(raw: dict) -> dict:
    cfg = validate_request(raw)
    alternatives = []
    definitions = [
        ("keep", "Keep contracted equipment", "Preserve the original scope and the requested demonstration date.", "contracted_3d", False, False),
        ("rent", "Rent compatible 3D equipment", "Recover the original scope with a camera rental and interface gateway.", "rental_3d", False, False),
        ("scope", "Propose a 2D rehearsal", "Show barcode and supervised 2D flow; defer the 3D localization claim.", "bench_2d", True, False),
        ("extend", "Propose a later demonstration", "Retain contracted equipment and ask the customer to accept a new date.", "contracted_3d", False, True),
    ]
    for plan_id, name, description, camera, reduced, extend in definitions:
        ready_day = cfg["camera_delay_days"] if camera == "contracted_3d" else CAMERAS[camera]["ready_day"]
        schedule = solve(build_tasks(camera, ready_day, reduced), {"software": cfg["engineer_start_day"] * SLOTS_PER_DAY})
        deadline = max(cfg["demo_day"], math.ceil(schedule["finish_day"])) if extend else cfg["demo_day"]
        extra = 1380 if camera == "rental_3d" else 0
        blockers = []
        approvals = []
        if cfg["part_weight_kg"] > 6:
            blockers.append("Workpiece exceeds the arm's declared 6 kg payload.")
        if cfg["part_weight_kg"] > 5:
            blockers.append("Workpiece exceeds the gripper's declared 5 kg limit.")
        if camera == "contracted_3d" and cfg["primary_unavailable"]:
            blockers.append("The contracted camera is marked unavailable.")
        if camera == "rental_3d" and not cfg["adapter_available"]:
            blockers.append("USB3 camera cannot connect to the GigE controller: required gateway is unavailable.")
        if schedule["finish_day"] > deadline:
            blockers.append(f"Finishes on working day {schedule['finish_day']:g}, after day {deadline}.")
        if extra > cfg["recovery_budget_usd"]:
            blockers.append(f"Additional recovery cost ${extra:,} exceeds the ${cfg['recovery_budget_usd']:,} budget.")
        if reduced and cfg["requires_3d"]:
            approvals.append("Customer must accept a reduced demonstration without 3D localization.")
        if extend and deadline != cfg["demo_day"]:
            approvals.append(f"Customer must accept day {deadline} instead of day {cfg['demo_day']}.")
        original_scope_met = not (reduced and cfg["requires_3d"])
        original_date_met = schedule["finish_day"] <= cfg["demo_day"]
        outcome = "blocked" if blockers else "approval_required" if approvals else "ready_to_propose"
        plan = {
            "id": plan_id, "name": name, "description": description, "camera": camera,
            "finish_day": schedule["finish_day"], "deadline_day": deadline,
            "finish_slot": schedule["finish_slot"], "extra_cost_usd": extra,
            "cost_breakdown": [{"item": "3D camera rental", "usd": 900}, {"item": "USB3 gateway", "usd": 180}, {"item": "Gateway configuration: 4 h × $75", "usd": 300}] if extra else [],
            "blockers": blockers, "approvals": approvals, "status": outcome,
            "operationally_feasible": not blockers,
            "original_scope_met": original_scope_met, "original_date_met": original_date_met,
            "slack_working_days": cfg["demo_day"] - schedule["finish_day"],
            "tasks": schedule["tasks"], "schedules_evaluated": schedule["schedules_evaluated"], "bom": _bom(camera),
            "runbook": [
                "Confirm the chosen scope and target date with the customer; attach sign-off outside this prototype.",
                f"Verify the actual inventory and availability of {CAMERAS[camera]['name']} before booking equipment.",
                "Complete mounting, I/O and interface checks recorded in the WBS.",
                "Run human-reviewed supervised safety checks before energizing the robot.",
                "Rehearse the chosen scenario and link observations to the agreed acceptance checklist.",
                ("Present a 2D rehearsal; explicitly defer the 3D localization requirement." if reduced and cfg["requires_3d"] else "Present 3D localization and barcode traceability using the agreed demonstration checklist."),
                "Record customer observations and issues; regenerate the plan when a constraint changes.",
            ],
        }
        alternatives.append(plan)
    ranked = [p for p in alternatives if p["operationally_feasible"]]
    ranked.sort(key=lambda p: (bool(p["approvals"]), not p["original_scope_met"], not p["original_date_met"], p["extra_cost_usd"], p["finish_day"]))
    revision = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:16]
    return {"schema_version": SCHEMA_VERSION, "revision": revision, "config": cfg,
            "recommended_id": ranked[0]["id"] if ranked else None,
            "alternatives": alternatives,
            "assumptions": ["Synthetic catalog, people, costs and task durations; not company or customer records.",
                            "Day 0 is project start. Two 4-hour working slots per day; overnight hours are excluded.",
                            "Each named person is exclusive while assigned. Task durations are fixed declared estimates.",
                            "Only explicit equipment, payload, interface, scope, budget and schedule constraints are checked.",
                            "This is planning support, not physical collision checking, safety certification or cycle-time prediction."],
            "engine": {"type": "Enumerated discrete resource-constrained scheduling", "slot_hours": SLOT_HOURS,
                       "ai_used": False, "provider_calls": 0}}


def export_markdown(record: dict, plan: dict, selected: bool = False) -> str:
    cfg = record["config"]
    lines = [f"# DemoShift · {plan['name']}", "", f"Customer: {cfg['customer']}", f"Customer objective: {cfg['goal']}",
             f"Plan revision: {record['revision']}", f"Status: {'Team-selected proposal' if selected else 'Candidate proposal'}; customer approval not recorded.",
             f"Target: day {plan['deadline_day']} · Finish: day {plan['finish_day']:g} · Additional recovery cost: ${plan['extra_cost_usd']:,}", ""]
    conditions = plan["blockers"] + plan["approvals"] or ["All declared constraints pass for this proposal."]
    lines += ["## Decision conditions", ""] + ["- " + row for row in conditions]
    lines += ["", "## Bill of materials", "", "| Item | Qty | Status | Declared constraint |", "|---|---:|---|---|"]
    for row in plan["bom"]:
        lines.append(f"| {row['item']} | {row['quantity']} | {row['status']} | {row['constraint']} |")
    lines += ["", "## Work breakdown and schedule", "", "| Task | Working days | Owner(s) | Output |", "|---|---|---|---|"]
    for task in plan["tasks"]:
        owners = ", ".join(PEOPLE[r] for r in task["resources"])
        lines.append(f"| {task['label']} | {task['start_slot']/2:g}–{task['end_slot']/2:g} | {owners} | {task['output']} |")
    lines += ["", "## Demonstration runbook", ""] + [f"{i}. {item}" for i, item in enumerate(plan["runbook"], 1)]
    lines += ["", "## Model assumptions", ""] + ["- " + row for row in record["assumptions"]]
    return "\n".join(lines) + "\n"
