---
name: jira-story-refiner
description: Refines a Jira user story into a technically feasible, layer-by-layer
  implementation plan for a Java application. Accepts a Jira ticket URL or pasted
  story text. Checks technical feasibility before presenting options. Writes a
  structured implementation plan as a Markdown file to the workspace.
  Invoke with /jira-story-refiner.
---

# Jira Story Refiner Skill

## Purpose

Transform a vague or non-technical Jira story into a structured, implementable
plan that an engineer can act on immediately. The skill:

- Loads the application manifest for context — no source code scanning
- Fetches the story from Jira or accepts pasted text
- Identifies gaps and clarifies using askQuestions (max 5 questions)
- Checks technical feasibility of every approach before presenting it
- Presents 2–3 feasible options with a tradeoff comparison
- Writes a Jira-ready implementation plan as a Markdown file

This is a single-story, single-session skill. Start a new session for each story.

## Prerequisites

- `app-manifest.yaml` must exist in the project root (run `/generate-context`
  or `/generate-context-microservice` first)
- For Jira URL input: `JIRA_TOKEN` environment variable must be set to a
  personal access token with read access to the project

## Steps

### Step 1 — Load application manifest

Read `app-manifest.yaml` from the project root.

Extract and hold in context:
- `app.name`, `app.type` (monolith-ear | microservice)
- `build.java_version`, `build.spring_boot_version` (if microservice)
- `ejb_layer` or `api` section (depending on app type)
- `messaging` section — queue/topic names, formats, volumes
- `database` — type, ORM, heavy_stored_procs flag
- `upstream` and `downstream` integration map
- `special_libs` — only those where present: true
- `constraints` list
- `migration.strangler_fig_phase`
- `functional_context` — summary, workflows, domain_entities, api_surface,
  stored_procedures

If `app-manifest.yaml` is not found, stop and tell the engineer:
> "app-manifest.yaml not found. Please run /generate-context (EAR) or
> /generate-context-microservice (Spring Boot) first, then retry."

If `manifest_meta.generated` is more than 90 days old, warn:
> "⚠ This manifest was generated on {date}. It may be stale. Consider
> refreshing it before proceeding. Continue anyway? (yes/no)"
> Wait for confirmation before continuing.

### Step 2 — Story intake

Determine how the story was provided:

**If a Jira URL was provided:**

Extract the issue key from the URL (e.g., `PROJ-1234` from
`https://jira.company.com/browse/PROJ-1234`).

Run the fetch script from the VS Code terminal:

```bash
python3 .github/skills/jira-story-refiner/fetch_jira_story.py <jira-url>
```

This outputs `jira-story-raw.txt` to the project root. Read the file.

If the fetch fails (missing token, network error, wrong URL), tell the engineer:
> "Could not fetch the story automatically. Please paste the story text
> directly into the chat and I will continue."
> Accept the pasted text and proceed.

**If story text was pasted directly:**
Use the pasted text as-is. Try to identify a ticket ID from the text
(e.g., a line starting with `PROJ-1234` or `[PROJ-1234]`). Use `manual` as
the ID if none is found.

**Story fields to extract:**
- Ticket ID (e.g., PROJ-1234)
- Summary / title
- Description (the "As a / I want / So that" or free-form text)
- Acceptance criteria (if present)
- Labels or components (if present in the fetch output)

### Step 3 — Gap analysis (internal — do not show to engineer)

Before asking any questions, analyse the story against the manifest silently.
Identify the most critical missing information using this checklist:

**Story gaps:**
- [ ] Are acceptance criteria present and specific enough to test?
- [ ] Is it clear which user role initiates the action?
- [ ] Are edge cases or error scenarios described?
- [ ] Is the expected data input/output format defined?
- [ ] Is it clear whether this is a new capability or a change to existing?

**Manifest alignment gaps:**
- [ ] Which app layer is primarily affected?
  (Web/Controller, EJB/Service, Repository, DB, MQ)
- [ ] Does the story touch any entity listed in `functional_context.domain_entities`?
- [ ] Does it touch any existing endpoint in `functional_context.api_surface`?
- [ ] Does it require integration with upstream or downstream apps?
- [ ] Does it affect any MQ queue listed in the manifest?
- [ ] Does it require DB changes (new table, schema change, stored proc)?
- [ ] Does it involve any special library (HL7, FOP, Drools, iText)?

Select the **top 3–5 gaps** to ask about. Do not ask about gaps you can
confidently infer from the story + manifest.

### Step 4 — Clarification via askQuestions

Use the **askQuestions** tool to present the top gaps identified in Step 3
as an interactive carousel. Frame each question concisely and include
a hint based on the manifest context.

Example questions (adapt to actual gaps found):

- "What triggers this workflow — a user action in the UI, an inbound MQ
  message, or a scheduled job?"

- "Should the result be persisted to the database, returned synchronously
  to the caller, or published to an outbound queue?"

- "Are there any validation rules that must pass before the operation
  proceeds? If so, should they go through the Drools rules engine or
  inline business logic?"

- "Does this change the message format on {queue_name}? If so, which
  downstream services consume that queue?"

- "Is this additive (new feature) or a change to existing behaviour in
  {workflow_name}?"

Do not ask more than 5 questions. If you have fewer than 3 genuine gaps,
proceed directly to Step 5.

### Step 5 — Feasibility checking

Read `.github/skills/jira-story-refiner/feasibility-rules.md` to load the
full ruleset. Then:

For each potential implementation approach you are considering (you should
have 2–4 candidates at this point), run all five checks from the rules file:

1. **Stack Check** — Does it fit the technology stack?
2. **Architecture Check** — Does it fit the layering and patterns?
3. **Contract Check** — Does it break existing API or MQ contracts?
4. **DB Check** — What database changes are required and are they safe?
5. **Cross-App Check** — Does it require changes to apps outside this team?

For each approach, record:
- Overall result: ✓ Feasible | ⚠ Feasible with caveats | ✗ Infeasible
- Failed checks with specific reason
- Caveats for warning-level checks

Discard approaches that fail any check as ✗ Infeasible. Keep all others
(including those with caveats) for presentation.

If fewer than 2 feasible approaches remain after checking, tell the engineer:
> "I could only find {n} feasible approach(es) given the current stack and
> constraints. Here is what I found and why the others were ruled out."
> Present the single option (or explain why none exist and what would need
> to change to unblock implementation).

### Step 6 — Option presentation and selection

Present the feasible approaches as a comparison. For each approach include:

**[Approach Name]** — one-line description

| Dimension | Details |
|---|---|
| Affected layers | e.g., Service + Repository + DB |
| DB changes | e.g., New Flyway migration required |
| Integration impact | e.g., No contract changes |
| Cross-team coordination | e.g., None / DBA required / {team} team |
| Key risk | e.g., Changes stored proc used by {other_workflow} |
| Feasibility | ✓ Feasible / ⚠ Feasible with caveats |

Show infeasible approaches separately at the bottom under a collapsed section:

**Ruled out:**
- {Approach name}: ✗ {specific reason from feasibility check}

Then use the **askQuestions** tool with two questions:

1. "Which approach do you want to proceed with? (provide the name or number)"
2. "What tradeoff are you accepting with this choice? (briefly describe)"

Do not proceed to Step 7 until the engineer has answered both questions.
This ensures deliberate decision-making rather than defaulting to option 1.

### Step 7 — Generate implementation plan

Using the selected approach and all gathered context, generate a complete
implementation plan following the exact format defined in
`.github/skills/jira-story-refiner/output-template.md`.

Determine the output filename:
- If a ticket ID was found: `{TICKET-ID}-refinement.md`
  (e.g., `PROJ-1234-refinement.md`)
- If no ticket ID: `story-refinement-{YYYY-MM-DD}.md`

Write the file to the project root. Do not ask for confirmation — writing
the plan is the expected outcome of selecting an approach.

After writing, tell the engineer:
> "Implementation plan written to {filename}. Open it to review, edit
> the Open Questions section with your PO, and paste the Acceptance
> Criteria section into the Jira ticket."

Clean up `jira-story-raw.txt` from the project root if it was created.

## Rules

- Never read .java or .class files
- Never load full source directories into context
- Always run all five feasibility checks before presenting any option
- Use askQuestions for all question gathering — do not ask as plain text
- Maximum 5 clarifying questions in Step 4
- Do not skip the engineer's tradeoff confirmation in Step 6
- The output .md file is always written — do not make it optional
- Layer naming in the plan must match app.type:
  - monolith-ear: Web → EJB Session Bean → JPA/JDBC → Oracle Stored Proc
  - microservice: REST Controller → Service → Repository → DB Migration
- If a story clearly spans multiple applications, flag it immediately in
  Step 3 and recommend splitting into separate stories before proceeding
- Clean up temporary files (jira-story-raw.txt) after plan is written
