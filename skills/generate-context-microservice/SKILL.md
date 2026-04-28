---
name: generate-context-microservice
description: Generates app-manifest.yaml and .github/copilot-instructions.md for a Spring Boot microservice deployed on AKS or EKS. Use when setting up or refreshing Copilot context for a microservice project. Invoke with /generate-context-microservice.
---

# Generate Context Microservice Skill

## Purpose

Create two files that give Copilot accurate, lightweight context about this
Spring Boot microservice without loading source code into context:

- `app-manifest.yaml` — machine-readable reference consumed by all skills
- `.github/copilot-instructions.md` — auto-loaded by Copilot in every session

## Expected Project Structure

This skill assumes a standard Spring Boot Maven or Gradle project:

```
project-root/
├── pom.xml                                   (Maven) or build.gradle (Gradle)
├── src/main/resources/application.yml         (or application.properties)
├── src/main/resources/application-*.yml       (profile overrides, optional)
├── src/main/resources/openapi.yaml            (OpenAPI spec, optional)
├── src/main/resources/db/migration/           (Flyway, optional)
├── src/main/resources/db/changelog/           (Liquibase, optional)
├── Dockerfile                                  (optional)
└── helm/ or k8s/                              (optional)
```

## Steps

### Step 1 — Run the scanner

Run this command from the project root in the VS Code terminal:

```bash
python3 .github/skills/generate-context-microservice/scan_springboot.py
```

This produces `scan-output.yaml` in the project root. Read the file and present a clear summary to the engineer, grouped by: build, API, messaging, database, and deployment. Ask: "Does this look accurate? Anything missing or incorrect?" Correct any errors the engineer identifies before continuing.

### Step 2 — Gather operational context with askQuestions

Use the **askQuestions** tool to present the following 7 questions to the engineer as an interactive carousel. Do not ask them as plain text — use the tool so the engineer can answer all questions in one interaction.

Questions for the askQuestions tool:

1. What business domain does this service serve? (e.g., claims processing, member management, payment gateway)

2. What team owns this service, and what is the primary contact email?

3. Which services or systems send requests or messages TO this service? List each with the integration type: REST API call or MQ/queue name. (e.g., "api-gateway → REST", "claims-processor → RabbitMQ: claims.inbound")

4. Which services or systems does this service call or send messages TO? List each with the integration type: REST API call or MQ/queue name. (e.g., "notification-service → REST", "audit-service → Kafka: audit.events")

5. Is this service a refactor or migration candidate? If yes, describe the target state and timeline. (e.g., "Migrate from RDS Oracle to Aurora Postgres — Q3 2026")

6. Are there any constraints other engineers must know before modifying this service? (e.g., SLA requirements, PCI scope, HIPAA boundary, shared library version locks, inter-team API contracts)

7. Are any API endpoints or message consumers particularly high-traffic or latency-sensitive? Describe volume or SLA if known. (e.g., "POST /claims — 500 req/sec peak, <200ms SLA")

### Step 3 — Gather functional context with askQuestions

Use the **askQuestions** tool again for a second carousel covering what the service *does*, not just how it is built. These answers populate `functional_context` in the manifest and are required for the Jira Story Refiner skill to assess technical feasibility accurately.

Questions for the askQuestions tool:

8. In 2-3 sentences, what does this service do in business terms? (e.g., "Receives submitted insurance claims, validates coverage eligibility, and routes approved claims to the billing queue for payment processing.")

9. What are the 3-5 core workflows or operations this service handles? Give each a short name and one-line description. (e.g., "Claim Submission — validates and persists a new claim from the intake queue")

10. What are the key business entities this service owns or manages? Give each a name and one-line description. (e.g., "Claim — represents a submitted insurance claim with full lifecycle tracking")

11. Does this service have an OpenAPI spec committed to the repo? If yes, give the file path. If no, list the key REST endpoints with HTTP verb, path, and one-line description. (e.g., "No spec — POST /claims submits a claim, GET /claims/{id} retrieves status")

12. Does the database use stored procedures or complex native queries? If yes, list the key ones with their purpose. (e.g., "sp_validate_coverage(member_id, service_date) — checks eligibility")

### Step 4 — Generate app-manifest.yaml

Combine scan-output.yaml with the engineer's answers from both askQuestions carousels. Generate app-manifest.yaml in the project root following the exact schema in manifest-template.yaml. Do not add or remove fields from the schema.

For `api.endpoints`: if an OpenAPI spec path was provided, read that file and extract the endpoint list. If no spec exists, use the endpoints provided in question 11.

### Step 5 — Generate .github/copilot-instructions.md

Generate from the manifest as flowing prose paragraphs — not YAML, not bullet points, not a header for every field.

Cover these topics in order:

1. **Service overview** — domain, team, what it does in business terms, deployment platform, migration status
2. **Core workflows** — the 3-5 business processes this service handles
3. **Domain model** — key business entities and their roles
4. **API surface** — existing endpoints (method, path, purpose); note high-traffic endpoints and their SLAs
5. **Messaging** — inbound queues/topics with format and volume; outbound queues/topics with downstream consumer
6. **Integration** — upstream services and how they connect; downstream services and how they connect
7. **Database** — type, ORM, migration tool, stored procedure usage; note Oracle-specific patterns if present
8. **Constraints** — SLA requirements, compliance boundaries, API contracts that must not change, version locks
9. **Special libraries** — only list libraries where present: true in the manifest

### Step 6 — Write files directly

Write both files immediately to the project root without printing their contents in chat and without asking for confirmation:

- Write `app-manifest.yaml` to the project root.
- Write `.github/copilot-instructions.md` to the `.github/` directory.
- Delete `scan-output.yaml` — it is a temporary artefact.

After writing, print only a short confirmation message listing the two files that were created.

## Rules

- Never read .java or .class files
- Never load full source directories into context
- Use the askQuestions tool for all question gathering — do not ask questions as plain chat text
- If a config file is missing, record it as a warning in the manifest rather than failing the skill
- If an OpenAPI spec is present, always read it to populate api.endpoints — do not ask the engineer to list endpoints manually if the spec exists
- copilot-instructions.md must be written in prose only — no YAML, no bullet lists
- app-manifest.yaml goes in the project root
- .github/copilot-instructions.md goes in the .github/ directory
- scan-output.yaml is temporary and must be deleted after the manifest is written
- Do not print file contents to chat at any step — write files directly and confirm with a short status message only
