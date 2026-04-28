---
name: generate-context-spa
description: Generates app-manifest.yaml and .github/copilot-instructions.md for a Spring Boot + React SPA full-stack application. Scans both the Java backend and React frontend. Use when setting up or refreshing Copilot context for a full-stack project. Invoke with /generate-context-spa.
---

# Generate Context SPA Skill

## Purpose

Create two files that give Copilot accurate, lightweight context about this full-stack application — covering both the Spring Boot backend API and the React frontend — without loading source code into context:

- `app-manifest.yaml` — machine-readable reference consumed by all skills
- `.github/copilot-instructions.md` — auto-loaded by Copilot in every session

## Expected Project Structure

This skill supports two common layouts. Detect which is in use during Step 1.

**Layout A — Monorepo (frontend lives inside the Java project):**

```
project-root/
├── pom.xml                              ← Maven build with frontend-maven-plugin
├── src/main/java/                       ← Spring Boot backend
├── src/main/resources/
│   ├── application.yml
│   └── static/                          ← Built React assets (served by Spring Boot)
└── frontend/                            ← React source
    ├── package.json
    ├── vite.config.ts (or webpack / craco)
    ├── tsconfig.json
    └── src/
```

**Layout B — Separate repos / modules (backend and frontend are independent):**

```
backend-repo/                            ← Spring Boot REST API
├── pom.xml
└── src/main/

frontend-repo/                           ← React SPA (separate deployment)
├── package.json
└── src/
```

If Layout B is detected (no `frontend/` directory and no `frontend-maven-plugin` in pom.xml), note it in the manifest and scan only what is available in the current workspace. Inform the engineer which parts were scanned.

## Steps

### Step 1 — Run the scanner

Run this command from the project root in the VS Code terminal:

```bash
python3 .github/skills/generate-context-spa/scan_spa.py
```

This produces `scan-output.yaml` in the project root. Read the file and present a clear summary to the engineer, grouped by: backend build, frontend stack, API, database, and deployment. Ask: "Does this look accurate? Anything missing or incorrect?" Correct any errors before continuing.

### Step 2 — Gather operational context with askQuestions

Use the **askQuestions** tool to present the following questions as an interactive carousel. Do not ask them as plain text.

**Questions for the askQuestions tool:**

1. What business domain does this application serve? (e.g., member portal, claims management, provider directory)

2. What team owns this application, and what is the primary contact email?

3. Who are the primary users of this SPA? (e.g., internal staff only, external customers, both — include any authentication context such as SSO, Active Directory, or public access)

4. Is the React frontend served by Spring Boot (same origin), or deployed separately to a CDN or static host (different origin)? (e.g., "Served from Spring Boot static resources", "Deployed to Azure Static Web Apps — separate from the API")

5. Which backend services does this frontend call beyond its own Spring Boot API? List each with the integration type. (e.g., "auth-service → OAuth2 token exchange", "notification-service → REST — triggered by form submission")

6. Is this application in a compliance boundary? (e.g., HIPAA — no PHI in browser local storage or query strings, PCI — payment fields must not touch our servers, none)

7. Are there any known performance or accessibility requirements? (e.g., "LCP < 2.5s on 4G", "WCAG 2.1 AA required for all new pages", "none defined")

### Step 3 — Gather functional and design context with askQuestions

Use the **askQuestions** tool for a second carousel covering what the application *does* and how it is designed. These answers populate `functional_context` and `design_system` in the manifest and are required for the Jira Story Refiner and any future Figma-to-UI skill to work accurately.

**Questions for the askQuestions tool:**

8.  In 2-3 sentences, what does this application do in business terms? (e.g., "Allows enrolled members to view their claims history, submit new claims with supporting documents, and track approval status in real time.")

9.  What are the 3-5 core user workflows this application supports? Give each a short name and one-line description. (e.g., "Claim Submission — member fills multi-step form and uploads documents")

10. What are the main pages or views in the application? List each with its route path and a one-line description. (e.g., "/claims — claims list with filter and search", "/claims/:id — claim detail with status timeline", "/claims/new — multi-step submission form")

11. Is there a Figma design file or design system linked to this project?
    If yes, provide the Figma file URL or design system name.
    If no, describe the component library and visual style in use.
    (e.g., "Figma: https://figma.com/file/ABC123 — uses our internal DS tokens",
           "No Figma — uses MUI v5 with company theme overrides",
           "No Figma — custom CSS with no component library")

12. Are there any existing React components or patterns engineers must follow
    when building new UI? List the key ones.
    (e.g., "All data tables use our <DataGrid> wrapper — never use raw MUI DataGrid",
           "Forms must use the <FormProvider> pattern from react-hook-form",
           "API calls must go through the useApi() hook — never use axios directly")

### Step 4 — Generate app-manifest.yaml

Combine scan-output.yaml with answers from both askQuestions carousels.
Generate app-manifest.yaml in the project root following the exact schema in manifest-template.yaml. Do not add or remove fields from the schema.

For `frontend.api_proxy_target`: populate from the proxy config detected in vite.config or webpack.config during the scan.

For `design_system.figma_url`: populate only if the engineer provided a URL in question 11. Do not attempt to access the URL.

For `functional_context.ui_pages`: populate from the engineer's answer to question 10. If the scan detected a React Router config, cross-reference it.

### Step 5 — Generate .github/copilot-instructions.md

Generate from the manifest as flowing prose — not YAML, not bullet points, not a header for every field.

Cover these topics in order:

1. **Application overview** — domain, team, who the users are, what it does in business terms, deployment mode (same-origin vs separate)
2. **Core user workflows** — the 3-5 workflows from question 9
3. **Frontend stack** — React version, language (TS/JS), build tool, state management, routing, UI library, HTTP client; note any mandatory patterns from question 12
4. **Page structure** — key pages with routes and purpose; note which are protected (auth-required) vs public
5. **Backend API** — Spring Boot version, REST endpoints, CORS config, auth mechanism; note high-traffic endpoints and SLAs
6. **Backend database** — type, ORM, migration tool, stored proc usage
7. **Integration** — upstream and downstream services beyond own backend
8. **Design system** — Figma file (if linked), component library, design token usage, accessibility requirements
9. **Compliance constraints** — HIPAA, PCI, or other boundaries from question 6; specific rules for what must not happen in the UI or API
10. **Special libraries** — only list libraries where present: true in manifest

### Step 6 — Write files directly

Write both files immediately to the project root without printing their contents in chat and without asking for confirmation:

- Write `app-manifest.yaml` to the project root.
- Write `.github/copilot-instructions.md` to the `.github/` directory.
- Delete `scan-output.yaml` — it is a temporary artefact.

After writing, print only a short confirmation message listing the two files that were created.

## Rules

- Never read .java or .class files
- Never load full source directories into context
- Use the askQuestions tool for all question gathering — never as plain text
- Scan both backend (pom.xml, application.yml) and frontend (package.json, vite/webpack config) — report what was found and what was missing
- If the project uses Layout B (separate repos), clearly mark the manifest sections that could not be scanned with "not scanned — separate repo"
- Do not attempt to access any Figma URL provided by the engineer
- copilot-instructions.md must be written in prose only — no YAML, no bullet lists
- app-manifest.yaml goes in the project root
- .github/copilot-instructions.md goes in the .github/ directory
- scan-output.yaml is temporary and must be deleted after the manifest is written
- Do not print file contents to chat at any step — write files directly and confirm with a short status message only
