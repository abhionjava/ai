---
name: generate-context
description: Generates app-manifest.yaml and .github/copilot-instructions.md
  for a Java EAR application built with Ant on a WebLogic split-directory
  structure. Use when setting up or refreshing Copilot context for an EAR
  project. Invoke with /generate-context.
---

# Generate Context Skill

## Purpose

Create two files that give Copilot accurate, lightweight context about this EAR
application without loading source code into context:

- `app-manifest.yaml` — machine-readable reference consumed by all skills
- `.github/copilot-instructions.md` — auto-loaded by Copilot in every session

## Expected Project Structure

This skill assumes a WebLogic split-directory layout built with Ant:

```
project-root/
├── build.xml
├── build.properties
├── ear/META-INF/application.xml
├── ear/META-INF/weblogic-application.xml
├── ejb/META-INF/ejb-jar.xml
├── ejb/META-INF/weblogic-ejb-jar.xml
├── web/WEB-INF/web.xml
├── web/WEB-INF/applicationContext.xml
└── lib/*.jar
```

## Steps

### Step 1 — Run the scanner

Run this command from the project root in the VS Code terminal:

```bash
python3 .github/skills/generate-context/scan_ear.py
```

This produces `scan-output.yaml` in the project root. Read the file and present
a summary to the engineer. Ask: "Does this look accurate? Anything missing or
incorrect?" Correct any errors the engineer identifies before continuing.

### Step 2 — Ask the engineer these 7 questions

Ask all 7. Do not skip or infer answers from context.

1. What business domain does this application serve?
   (e.g., claims processing, member management, billing)

2. What team owns this application, and who is the primary contact email?

3. Which application(s) send messages to the inbound MDB queues found by
   the scanner?

4. Which application(s) consume your outbound messages or call your APIs?

5. Is this a strangler-fig migration candidate? If yes, which module would be
   extracted first and why?

6. What are the known blockers to migration?
   (other team dependencies, regulatory constraints, data ownership issues)

7. Are any MQ flows particularly high-volume or latency-sensitive? Describe
   volume if known (messages/sec, peak periods).

### Step 2b — Ask the engineer these 5 functional context questions

These are asked after Step 2. They capture what the application *does*, not
just how it is built. This section populates `functional_context` in the
manifest and is required for the Jira Story Refiner skill to assess technical
feasibility accurately.

Ask all 5. Do not skip or infer answers from source code.

8.  In 2-3 sentences, what does this application do in business terms?
    (e.g., "Receives HL7 claims from payers, validates against member
    eligibility, and routes approved claims to the billing system")

9.  What are the 3-5 core workflows or business processes this application
    handles? List each with a one-line description.
    (e.g., "Claim intake — receives and validates inbound HL7 messages")

10. What are the key business entities this application owns or manages?
    List each with a one-line description.
    (e.g., "Claim — represents a submitted insurance claim with status tracking")

11. List any existing REST endpoints or key EJB session bean methods that
    engineers commonly work with. Include the method signature or HTTP verb
    and path where known.
    (e.g., "POST /claims — submits a new claim",
           "ClaimsProcessorBean.validateClaim(ClaimDTO) — validates claim fields")

12. If the database uses stored procedures, list the key ones and their
    purpose in one line each.
    (e.g., "sp_validate_claim(claim_id) — checks eligibility against member table",
           "sp_update_claim_status(claim_id, status) — updates claim lifecycle state")

### Step 3 — Generate app-manifest.yaml

Combine scan-output.yaml with answers from Step 2 and Step 2b. Generate
app-manifest.yaml in the project root following the exact schema defined in
manifest-template.yaml. Do not add or remove fields from the schema.

### Step 4 — Generate .github/copilot-instructions.md

Generate from the manifest as flowing prose paragraphs — not YAML, not bullet
points, not headers for every field.

The file must cover these topics in order:

1. **Application overview** — domain, team, application type, migration status,
   and what the application does in business terms
2. **Core workflows** — the 3-5 business processes the application handles
3. **Domain model** — key business entities and their roles
4. **Architecture** — EJB session beans, MDB queues with JNDI names and message
   formats, web layer technology
5. **API and EJB surface** — existing endpoints and session bean methods
6. **Integration** — upstream dependencies (what sends to this app) and
   downstream dependencies (what this app feeds), with integration type
   (MQ or API)
7. **Database** — type, datasource JNDI, stored procedure usage, ORM
8. **Migration context** — what must not be broken, extraction candidates with
   rationale, known blockers
9. **Special libraries** — only list libraries where present: true in the manifest

### Step 5 — Confirm and write

Show the engineer a preview of both files. Ask: "Shall I write these to the
project?" Only write files after explicit confirmation.

After writing, delete scan-output.yaml — it is a temporary artefact.

## Rules

- Never read .java or .class files
- Never load full source directories into context
- If a descriptor file is missing, record it as a warning in the manifest
  rather than failing the skill
- copilot-instructions.md must be written in prose only — no YAML, no
  bullet lists
- app-manifest.yaml goes in the project root
- .github/copilot-instructions.md goes in the .github/ directory
- scan-output.yaml is temporary and must be deleted after the manifest is written
