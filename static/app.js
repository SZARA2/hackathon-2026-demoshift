"use strict";
let state = null;
let inspectedId = null;
let currentTab = "schedule";
let aiProposal = null;
const $ = id => document.getElementById(id);
const money = value => new Intl.NumberFormat("en-US", {style: "currency", currency: "USD", maximumFractionDigits: 0}).format(value);
const numeric = ["demo_day", "camera_delay_days", "engineer_start_day", "part_weight_kg", "recovery_budget_usd"];
const boolean = ["requires_3d", "primary_unavailable", "adapter_available"];
const names = {demo_day:"Demo day",camera_delay_days:"Camera ready day",engineer_start_day:"Engineer starts day",part_weight_kg:"Part weight (kg)",recovery_budget_usd:"Recovery budget (USD)",requires_3d:"3D localization required",primary_unavailable:"Contracted camera unavailable",adapter_available:"Interface gateway available"};

function el(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = String(text);
  return item;
}
function message(text, error=false) { $("message").textContent=text; $("message").className="notice"+(error?" error":""); $("message").hidden=false; }
async function api(path, body) {
  const response = await fetch("api/"+path, body === undefined ? {credentials:"same-origin"} : {method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  let result;
  try { result = await response.json(); } catch (_) { throw new Error("The server did not return a valid response. Please retry."); }
  if (!response.ok) throw new Error(result.error || "The request could not be completed.");
  return result;
}
function fillForm(cfg) { numeric.forEach(key => $(key).value=cfg[key]); boolean.forEach(key => $(key).checked=cfg[key]); }
function readForm() {
  const result = {...state.config};
  numeric.forEach(key => result[key]=Number($(key).value)); boolean.forEach(key => result[key]=$(key).checked);
  return result;
}
function planById(id) { return state.alternatives.find(plan => plan.id===id); }
function render() {
  fillForm(state.config);
  $("customer-name").textContent=state.config.customer;
  $("customer-goal").textContent=state.config.goal;
  $("requested-date").textContent="Working day "+state.config.demo_day;
  const feasible=state.alternatives.filter(plan=>plan.operationally_feasible);
  const full=feasible.filter(plan=>plan.original_scope_met);
  $("metric-feasible").textContent=feasible.length+" / 4";
  $("metric-feasible-note").textContent=feasible.some(plan=>plan.approvals.length) ? "includes conditional proposals" : "under declared constraints";
  $("metric-finish").textContent=full.length ? "Day "+Math.min(...full.map(plan=>plan.finish_day)) : "None";
  $("metric-state").textContent=state.selected_plan_id ? "Proposal selected" : feasible.length ? "Review proposals" : "No feasible proposal";
  $("metric-state-note").textContent=state.selected_plan_id ? "Customer sign-off still separate" : "Choose the next customer conversation";
  $("revision").textContent="REV "+state.revision.slice(0,8).toUpperCase();
  $("ai-status").textContent=state.ai.configured ? "AI connected · review required" : "Constraint engine · AI not connected";
  $("ai-status").className="pill"+(state.ai.configured?"":" warning");
  $("ai-note").textContent=state.ai.configured ? "Your brief is sent to the configured model. Review its proposed constraints before applying them." : "AI requires a server-side model connection. Use the editable constraints or the sample scenarios now.";
  $("interpret-button").disabled=!state.ai.configured;
  $("save-status").textContent="Saved · revision "+state.revision.slice(0,8);
  if (!inspectedId || !planById(inspectedId)) inspectedId=state.selected_plan_id || state.recommended_id || "keep";
  renderAlternatives(); renderDetails(); renderHistory();
  $("assumptions").replaceChildren(...state.assumptions.map(item=>el("li","",item)));
  const count=state.alternatives.reduce((n,plan)=>n+plan.schedules_evaluated,0);
  $("solver-note").textContent="Engine: "+state.engine.type+". "+count+" complete priority schedules evaluated across four alternatives. AI determines neither feasibility nor customer approval.";
}
function renderAlternatives() {
  $("alternatives-grid").replaceChildren(...state.alternatives.map(plan=>{
    const button=el("button","alternative"+(plan.id===inspectedId?" inspected":""));
    button.type="button"; button.setAttribute("aria-pressed",String(plan.id===inspectedId));
    const status=el("div","status "+plan.status); status.append(el("i","status-dot"));
    status.append(document.createTextNode({blocked:"Constraint conflict",approval_required:"Customer decision needed",ready_to_propose:"Declared constraints pass"}[plan.status]));
    button.append(status,el("h3","",plan.name),el("p","",plan.description));
    const numbers=el("div","alt-numbers");
    const finish=el("div");finish.append(el("strong","","D"+plan.finish_day),el("small","","planned finish"));
    const cost=el("div");cost.append(el("strong","",money(plan.extra_cost_usd)),el("small","","additional cost"));
    numbers.append(finish,cost);button.append(numbers);
    if (state.selected_plan_id===plan.id) button.append(el("div","selected-label","TEAM-SELECTED PROPOSAL"));
    let bottom=plan.blockers.length ? plan.blockers[0] : plan.approvals.length ? plan.approvals[0] : "Original date and scope preserved.";
    if (state.recommended_id===plan.id) bottom="Suggested starting point · "+bottom;
    button.append(el("div","alt-bottom"+(state.recommended_id===plan.id?" recommended":""),bottom));
    button.addEventListener("click",()=>{inspectedId=plan.id;renderAlternatives();renderDetails();});
    return button;
  }));
}
function renderDetails() {
  const plan=planById(inspectedId);
  $("detail-title").textContent=plan.name;
  $("detail-description").textContent=plan.description;
  $("detail-finish").textContent="Working day "+plan.finish_day;
  $("detail-cost").textContent=money(plan.extra_cost_usd);
  const conditions=[...plan.blockers.map(item=>el("div","condition blocker",item)),...plan.approvals.map(item=>el("div","condition",item))];
  if (!conditions.length) conditions.push(el("div","condition pass","All declared constraints pass. This is a proposal; customer acceptance has not been recorded."));
  $("detail-conditions").replaceChildren(...conditions);
  $("select-button").disabled=!plan.operationally_feasible || state.selected_plan_id===plan.id;
  $("select-button").textContent=state.selected_plan_id===plan.id ? "Proposal selected ✓" : plan.operationally_feasible ? "Select this proposal" : "Cannot select: conflicts";
  $("export-markdown").href="api/export?plan="+encodeURIComponent(plan.id);
  $("export-json").href="api/export?plan="+encodeURIComponent(plan.id)+"&format=json";
  renderGantt(plan);
  $("wbs-body").replaceChildren(...plan.tasks.map(task=>{
    const row=el("tr");row.append(el("td","",task.label),el("td","",task.resources.map(resource=>state.people[resource]).join(" / ")),el("td","",task.output));return row;
  }));
  $("bom-body").replaceChildren(...plan.bom.map(item=>{
    const row=el("tr");row.append(el("td","",item.item),el("td","",item.quantity),el("td","",item.status),el("td","",item.constraint));return row;
  }));
  $("cost-breakdown").replaceChildren(...(plan.cost_breakdown.length ? [el("h3","","Additional recovery budget"),...plan.cost_breakdown.map(item=>el("p","",item.item+": "+money(item.usd))),el("p","","Total: "+money(plan.extra_cost_usd)+" · estimates only, no purchase placed.")] : [el("p","","No additional procurement cost is included in this synthetic proposal. Existing assets are assumed available as declared.")]));
  $("runbook-list").replaceChildren(...plan.runbook.map(item=>el("li","",item)));
}
function renderGantt(plan) {
  const horizon=Math.max(state.config.demo_day,Math.ceil(plan.finish_day));
  const container=$("gantt");container.replaceChildren();
  const header=el("div","gantt-row gantt-header");header.append(el("div","gantt-label","Work package · estimated effort"));
  const ticks=el("div","gantt-ticks");for(let d=0;d<=horizon;d++)ticks.append(el("span","",String(d)));header.append(ticks);container.append(header);
  plan.tasks.forEach(task=>{
    const row=el("div","gantt-row"),label=el("div","gantt-label",task.label);label.append(el("small","",task.hours+"h"));
    const track=el("div","gantt-track");track.style.setProperty("--day-width",100/horizon+"%");
    const bar=el("div","gantt-bar "+task.resources[0]);bar.style.left=100*(task.start_slot/2)/horizon+"%";bar.style.width=100*((task.end_slot-task.start_slot)/2)/horizon+"%";
    bar.title=task.label+": day "+task.start_slot/2+"–"+task.end_slot/2+" · "+task.resources.map(r=>state.people[r]).join(" + ");
    bar.setAttribute("role","img");bar.setAttribute("aria-label",bar.title);track.append(bar);row.append(label,track);container.append(row);
  });
}
function renderHistory() {
  $("history-list").replaceChildren(...state.events.map(event=>{
    const item=el("li"),detail=event.detail;
    const title=event.kind==="created"?"Original customer brief recorded":event.kind==="replanned"?"Constraints changed · proposals recalculated":"Operating proposal selected";
    item.append(el("strong","",title),el("small","",new Date(event.at*1000).toLocaleString(undefined,{dateStyle:"medium",timeStyle:"short"})));
    if (event.kind==="replanned") {
      const keys=Object.keys(detail.changes||{});
      item.append(el("p","",keys.length?keys.map(key=>(names[key]||key)+": "+detail.changes[key].from+" → "+detail.changes[key].to).join(" · "):"Same constraints replayed. Previous proposal selection cleared."));
    } else if(event.kind==="proposal_selected") item.append(el("p","",(planById(detail.plan_id)?.name||detail.plan_id)+" · customer approval not recorded."));
    else item.append(el("p","","Synthetic 3D part localization and barcode traceability PoC."));
    return item;
  }));
}
async function replan(config) {
  const button=$("replan-button");button.disabled=true;button.textContent="Checking declared constraints…";
  try {
    state=await api("replan",{expected_analysis_id:state.analysis_id,config});
    inspectedId=state.recommended_id||"keep";aiProposal=null;$("ai-proposal").hidden=true;render();
    message("Four proposals recomputed. The WBS, equipment list and runbook now share this revision. Previous selection cleared.");
  } catch(error){message(error.message,true);}
  finally{button.disabled=false;button.textContent="Recompute proposals →";}
}
$("constraints-form").addEventListener("submit",event=>{event.preventDefault();if(state&&event.currentTarget.reportValidity())replan(readForm());});
document.querySelectorAll("[data-scenario]").forEach(button=>button.addEventListener("click",()=>{
  if(!state)return;
  const cfg={...state.config};
  if(button.dataset.scenario==="camera"){cfg.camera_delay_days=5;cfg.primary_unavailable=false;cfg.engineer_start_day=0;cfg.demo_day=7;cfg.adapter_available=true;cfg.recovery_budget_usd=1500;cfg.part_weight_kg=2;cfg.requires_3d=true;}
  else if(button.dataset.scenario==="engineer"){cfg.engineer_start_day=4;}
  else{Object.assign(cfg,{demo_day:7,camera_delay_days:0,primary_unavailable:false,adapter_available:true,engineer_start_day:0,part_weight_kg:2,requires_3d:true,recovery_budget_usd:1500});}
  replan(cfg);
}));
$("select-button").addEventListener("click",async()=>{
  if(!state)return;const plan=planById(inspectedId);
  if(plan.approvals.length&&!window.confirm("This proposal changes the customer promise. Select it for the team to discuss? Customer approval will remain unrecorded.\n\n"+plan.approvals.join("\n")))return;
  $("select-button").disabled=true;
  try{state=await api("select",{expected_analysis_id:state.analysis_id,plan_id:plan.id,acknowledge_customer_approval_needed:!!plan.approvals.length});render();message("Operating proposal saved. Export the consistent BOM, WBS and runbook for the customer conversation. Customer sign-off remains separate.");}
  catch(error){message(error.message,true);$("select-button").disabled=false;}
});
document.querySelectorAll("[data-tab]").forEach(button=>button.addEventListener("click",()=>{
  currentTab=button.dataset.tab;
  document.querySelectorAll("[data-tab]").forEach(tab=>tab.setAttribute("aria-selected",String(tab.dataset.tab===currentTab)));
  ["schedule","equipment","runbook"].forEach(tab=>$(tab+"-panel").hidden=tab!==currentTab);
}));
$("interpret-button").addEventListener("click",async()=>{
  if(!state)return;const button=$("interpret-button");button.disabled=true;button.textContent="Requesting model proposal…";
  $("message").hidden=true;
  $("ai-proposal").hidden=true;
  try{
    aiProposal=await api("interpret",{expected_analysis_id:state.analysis_id,brief:$("brief").value});
    const panel=$("ai-proposal");panel.replaceChildren(el("strong","","Review proposed constraint changes"));
    const changes=Object.entries(aiProposal.changes);
    panel.append(el("p","",aiProposal.explanation));
    const list=el("ul");changes.forEach(([key,value])=>{const row=el("li","",names[key]+": "+state.config[key]+" → "+value);if(aiProposal.evidence?.[key])row.append(el("small",""," · source: “"+aiProposal.evidence[key]+"”"));list.append(row);});panel.append(list);
    if(!changes.length)panel.append(el("p","","No supported change was extracted. Edit the declared constraints directly."));
    panel.append(el("p","","Actual model response · "+aiProposal.model+" · "+(aiProposal.elapsed_ms/1000).toFixed(1)+"s. Not applied to the saved plan."));
    const details=el("details"),summary=el("summary","","Model response and usage");details.append(summary,el("pre","",JSON.stringify({response:aiProposal.raw_response,usage:aiProposal.usage},null,2)));panel.append(details);
    if(changes.length){const apply=el("button","button primary","Apply reviewed changes & replan →");apply.type="button";apply.addEventListener("click",()=>{if(aiProposal.based_on_analysis_id!==state.analysis_id)return message("This proposal was based on an older plan. Request a new model proposal.",true);replan({...state.config,...aiProposal.changes});});panel.append(apply);}
    panel.hidden=false;
  }catch(error){message(error.message,true);}
  finally{button.disabled=!state.ai.configured;button.textContent="Review AI changes ↗";}
});
api("state").then(result=>{state=result;render();}).catch(error=>{message(error.message,true);$("save-status").textContent="Connection failed";$("interpret-button").disabled=true;$("replan-button").disabled=true;$("select-button").disabled=true;});
