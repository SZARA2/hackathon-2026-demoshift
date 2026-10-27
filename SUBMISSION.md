# DemoShift — Customer promises, executable plans

## Elevator pitch

When equipment or customer requirements change, DemoShift helps robotics teams choose an executable recovery plan and regenerate the schedule, equipment list and runbook from one consistent revision.

## Inspiration

A convincing robotics demonstration is an operational commitment. The team must align a customer scenario, compatible equipment, specialist time, rehearsal, evidence and a promised date. A single camera delay can leave the equipment list, work breakdown and customer-facing plan describing different realities.

My background spans robotics solutions, customer demonstrations, equipment and cell configuration, and cross-functional project coordination. DemoShift translates those recurring coordination decisions into a small, explicit planning workflow. The public example uses an independent synthetic catalog and invented customer scenario.

## What it does

DemoShift starts with a customer's 3D localization and barcode-traceability goal. A natural-language request is sent to a configured real model to propose a structured constraint change. The user reviews that proposal before the operational model is changed.

The application then computes four alternatives: retain the contracted equipment, rent a compatible 3D camera with its required interface gateway, propose a reduced 2D rehearsal, or propose a later demonstration. Each alternative includes an actual resource-constrained schedule, a bill of materials, a work breakdown and a demonstration runbook. Declared payload, interface, availability, budget and deadline failures remain visible, and infeasible alternatives cannot be selected.

Customer agreement is explicit. A team can select a reduced-scope or later-date proposal for discussion, while the interface and exported operating pack continue to show that customer sign-off has not been recorded. A later replan invalidates the selected proposal and retains the decision trail.

## How it is built

The frontend is an accessible responsive HTML, CSS and JavaScript application. The Python backend uses a discrete four-hour working-time model, enumerating topological scheduling priorities to find the shortest resource-feasible schedule for each small fixed alternative. A person cannot be double-booked and camera-dependent work cannot start before equipment is available.

An OpenAI-compatible server-side adapter handles actual AI requests. The structured parser accepts only a whitelist of typed constraints and requires a verbatim source quote for every proposed field. Explicit numbers are checked against the field-specific source context, so an off-by-one day or a fabricated requirement is rejected. Unsupported equipment, tasks or arbitrary instructions cannot become operational capabilities. The model structures the request; deterministic constraint checks decide feasibility.

SQLite stores isolated browser-session plans, unadopted model proposals and action history. Random HttpOnly SameSite cookies, hashed token storage, origin validation, JSON-only writes and version checks keep sessions and concurrent edits separate. Exports are generated from the same saved plan revision as the displayed WBS and equipment list.

## What makes the workflow useful

This project does not claim to invent scheduling, equipment configuration or change management. Its product hypothesis is that a robotics solutions lead benefits from seeing the customer promise, physical-interface assumptions, specialist schedule and recovery choices in one short decision loop. The most important output is a plan the team can use for the next customer conversation, with the required decisions visible.

## What we verified

In the synthetic delayed-camera case, the original full-scope plan finishes on day 8.5 and misses the requested day-7 demonstration. The compatible rental alternative finishes on day 5.5 with $1,380 in declared recovery estimates. The 2D alternative finishes on day 4.5 but leaves the 3D customer requirement outstanding. A later-date alternative proposes day 9.

Twenty-five local unit and HTTP API tests pass, covering resource conflicts, equipment release, interface and payload constraints, budget, deterministic replay, export consistency, persistent independent sessions, stale writes, AI request budgets, source-value grounding and invalid model proposals. These results establish behavior of this synthetic planning model; they do not establish real robot performance or business savings.

## Remaining submission fields to fill from verified evidence

- Public demo URL: deployment operator to verify.
- Public repository URL and source commit: publishing operator to verify.
- Real AI model and request evidence: record on the deployed service.
- Required Vultr VM resource and deployment evidence: verify before submission.
- Video, presentation and cover: attach the actual published artifacts.
- Organizer receipt: verify after final submission.

## Built with

Python standard library · SQLite · HTML · CSS · JavaScript · server-side OpenAI-compatible inference adapter. Add the **actual verified** model and cloud runtime after deployment; configuration support alone is not proof of use.

## Next

Validate the declared task model with independent robotics PoC leads, compare the workflow with their existing WBS-and-equipment process, and measure constraint violations and cross-document inconsistencies. Expand the catalog only after the required interface and operating assumptions can be reviewed explicitly.
