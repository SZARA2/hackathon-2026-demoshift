# DemoShift screen recording script

Target: approximately **3 minutes 20 seconds**. Confirm the event's final duration requirement before recording. This script assumes that a real model connection and the required Vultr deployment have been verified; replace those claims with the actual evidence shown. Do not record a fixture response as a live model.

## 0:00–0:25 · The operational problem

**Screen:** original customer promise and baseline metrics.

“A robotics demo is a promise made across people, equipment and a customer's process. When one part changes, a project manager often has to update the equipment list, schedule and demo plan separately. DemoShift keeps those decisions connected. This public example is a synthetic 3D localization and barcode-traceability PoC, planned for working day seven.”

## 0:25–1:00 · From a change request to reviewed constraints

**Screen:** type the change below and click **Review AI changes**. Show the actual returned model name, response and usage.

> The contracted camera will not be ready until day 5. Keep the demonstration on day 7, with a recovery budget of $1,500.

“The customer date stays the same, but the contracted camera will arrive on day five. The connected model turns that request into a candidate constraint patch. It has not changed the plan. I can inspect exactly what it extracted and apply the changes only after reviewing them. Unsupported equipment and fields are rejected.”

**Action:** inspect the proposed fields, then click **Apply reviewed changes & replan**. If the model returns a mistaken value, show the correction honestly or retake after fixing the parser; do not conceal an invalid response behind a scripted substitute.

## 1:00–1:40 · Compute alternatives, including the uncomfortable ones

**Screen:** four proposal cards. Click the blocked original plan, then the rental.

“Now the constraint engine recomputes the operating choices. Keeping the original camera finishes on day eight and a half, so it cannot meet the original deadline. Renting the compatible 3D camera finishes on day five and a half, with thirteen hundred and eighty dollars in declared recovery costs. A two-dimensional rehearsal is faster, but it does not fulfill the customer's 3D requirement. Moving the demo to day nine is another proposal that needs the customer's agreement. These are explicit trade-offs, not four optimistic paragraphs.”

## 1:40–2:15 · Show actual compatibility and resource checks

**Screen:** inspect rental WBS. Uncheck **interface gateway available**, recompute, and show rental blocker. Restore the gateway and recompute.

“The schedule allocates named people and honors dependencies and equipment release dates. Perception calibration cannot happen before the camera is mounted, and the integration engineer cannot be double-booked. The rental camera also has a different interface. If its gateway is unavailable, the rental option is blocked. An AI explanation cannot make that incompatible configuration work.”

## 2:15–2:55 · One selected proposal, one operating pack

**Screen:** select the rental. Open Equipment and Runbook tabs; export Markdown or JSON. Refresh the browser and show persistence.

“I select the rental as the team's operating proposal. The same saved revision gives us the equipment list, the scheduled work packages and the rehearsal runbook. Exporting the pack preserves those IDs and conditions. Selecting a proposal does not invent customer sign-off. If we choose a reduced scope or a new date, the application continues to display that outstanding decision. Refreshing restores this browser's plan from SQLite.”

## 2:55–3:20 · Evidence and close

**Screen:** decision trail, assumptions and verified deployment evidence or architecture slide.

“The prototype passes twenty-five unit and HTTP API tests, including resource conflicts, interface and payload limits, isolated persistent sessions, source-grounded AI proposals and stale updates. The catalog and durations are synthetic; this is planning support, not robot simulation or safety certification. The goal is practical: when a robotics PoC changes, give the team a defensible next plan and a clear next conversation with the customer.”

## Recording evidence checklist

- Start from the original saved baseline, not a previously selected plan.
- Confirm AI is connected and show an actual unadopted response before applying it.
- Show the deadline failure and the interface-gateway failure.
- Capture the populated Gantt, BOM, runbook and exported file.
- Show the required Vultr VM/deployment proof separately, without exposing secrets.
- Use the public licensed code revision that matches the recorded application.
- Keep customer approval, physical validation and real commercial results unclaimed.
