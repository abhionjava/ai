# Output Template — Jira Story Refiner

Replace all `{placeholders}` with actual content. Do not add or remove sections.

Output filename: `{TICKET-ID}-refinement.md` (e.g., `PROJ-1234-refinement.md`)
Output location: project root

---
<!-- ═══════════════════════════════════════════════════════════════════════ -->
<!-- TEMPLATE BEGINS — copy everything below this line into the output file -->
<!-- ═══════════════════════════════════════════════════════════════════════ -->

# Story Refinement: {TICKET-ID}

> **{Story summary / title}**
> App: `{app.name}` · Type: `{app.type}` · Domain: `{app.domain}`
> Refined: {YYYY-MM-DD} · Engineer: _(add your name)_

---

## Rewritten Acceptance Criteria

_Technical rewrite of the original story criteria. Written in Given/When/Then format. Specific enough to form the basis of a test plan._

**Given** {precondition — system state, existing data, or user role}
**When** {action — API call, MQ message received, UI interaction, scheduled trigger}
**Then** {expected outcome — data persisted, response returned, message published, error raised}

**Additional criteria:**
- {Criterion 2 — edge case or error scenario}
- {Criterion 3 — validation rule or constraint}
- {Criterion N — add as many as needed}

**Out of scope for this story:**
- {Explicitly excluded item 1}
- {Explicitly excluded item 2}

---

## Selected Approach

**{Approach name}**

{One paragraph describing the approach: what it does, which layers it touches, and why it was chosen over the alternatives.}

### Tradeoff Accepted

> "{Engineer's stated tradeoff from Step 6 of the skill}"

### Ruled-Out Approaches

| Approach | Reason Ruled Out |
|---|---|
| {Approach B} | {Specific feasibility check that failed} |
| {Approach C} | {Specific feasibility check that failed} |

---

## Affected Components

_List only components that will be created or modified. Do not list components that are read-only or unchanged._

| Component | Type | Change |
|---|---|---|
| `{ClassName}` | {Controller / Service / Session Bean / MDB / Repository / Entity} | {New / Modify / Extend} |
| `{TableOrProc}` | {DB Table / Stored Proc / Flyway Migration / JPA Entity} | {New / Modify} |
| `{QueueOrEndpoint}` | {REST Endpoint / MQ Queue / Kafka Topic} | {New / Modify} |

---

## Implementation Steps

_Steps are ordered. Complete each layer before moving to the next.
Layer naming follows app type: EAR uses EJB layering; microservice uses
Spring Boot layering._

<!-- ── FOR MICROSERVICE ─────────────────────────────────────────── -->

### Layer 1: REST Controller

> _Skip if no new or modified endpoint is required._

1. {Step — e.g., "Add `POST /claims/{id}/approve` endpoint to `ClaimsController`"}
2. {Step — e.g., "Accept `ApprovalRequestDTO` as request body"}
3. {Step — e.g., "Validate `@NotNull claimId` and `@NotBlank reason` using Bean Validation"}
4. {Step — e.g., "Delegate to `ClaimsService.approveClaim(claimId, reason)`"}
5. {Step — e.g., "Return `202 Accepted` with `ApprovalResponseDTO`"}

### Layer 2: Service

1. {Step — e.g., "Add `approveClaim(Long claimId, String reason)` to `ClaimsService`"}
2. {Step — e.g., "Load `Claim` entity via `ClaimsRepository.findById(claimId)` — throw `ClaimNotFoundException` if not found"}
3. {Step — e.g., "Validate claim is in SUBMITTED state — throw `InvalidClaimStateException` if not"}
4. {Step — e.g., "Update status to APPROVED, set `approvedBy` and `approvedAt`"}
5. {Step — e.g., "Publish `ClaimApprovedEvent` to `claims.approved` topic via `ClaimEventPublisher`"}
6. {Step — e.g., "Return `ApprovalResponseDTO` with updated claim status"}

### Layer 3: Repository

> _Skip if no new query is required._

1. {Step — e.g., "Add `findByIdAndStatus(Long id, ClaimStatus status)` to `ClaimsRepository`"}
2. {Step — e.g., "Annotate with `@Lock(LockModeType.PESSIMISTIC_WRITE)` to prevent concurrent approvals"}

### Layer 4: Database

> _Skip if no schema change is required._

1. {Step — e.g., "Create Flyway migration `V{next}__add_claim_approval_fields.sql`"}
2. {Step — e.g., "Add columns: `approved_by VARCHAR(100)`, `approved_at TIMESTAMP`"}
3. {Step — e.g., "Both columns nullable — existing rows are unaffected"}


---

## Database Changes

> _Complete this section even if the change is "none required"._

**Schema changes:** {None required | List changes}

**Stored procedures:** {None required | List new or modified procs with signature}

**Migration script:** {None required | Flyway `V{n}__description.sql` | Liquibase changeset}

**Backward compatibility:** {Describe whether existing data and callers are unaffected}

**DBA coordination required:** {Yes / No}
{If yes: describe what needs to be raised as a DBA ticket}

---

## Integration Impact

### API Changes

| Endpoint | Change | Callers Affected |
|---|---|---|
| {method} {path} | {New / Modified / Unchanged} | {Upstream service names or "none"} |

### Messaging Changes

| Queue / Topic | Change | Consumers Affected |
|---|---|---|
| {queue_name} | {New / Modified format / New field / Unchanged} | {Downstream service names or "none"} |

### Coordination Required

{List each team or system that needs to be notified or involved before deployment.
If none, write "None — this change is self-contained."}

- **{Team name}**: {What they need to do and when}
- **DBA team**: {What DBA change management ticket to raise, if applicable}
- **DevOps / Platform**: {Any infra changes — new queues, new env vars, K8s config}

---

## Constraints and Risks

_Populated from feasibility check warnings (⚠). Each risk should have a
mitigation noted._

| Risk | Severity | Mitigation |
|---|---|---|
| {Risk from feasibility check} | High / Medium / Low | {Mitigation action} |
| {e.g., "High-volume queue affected"} | High | {e.g., "Load test in staging before prod deployment"} |
| {e.g., "Touching a strangler-fig extraction candidate"} | Medium | {e.g., "Confirm with architect whether feature should be built in target microservice"} |

---

## Open Questions

_Questions for the Product Owner or other stakeholders that must be answered
before implementation begins. Copy this section into the Jira comment._

1. {Question for PO — e.g., "Should a rejected claim be resubmittable after approval is denied?"}
2. {Question for PO — e.g., "Is there an audit log requirement for the approval action?"}
3. {Question for other team — e.g., "Confirm with {team} that they can handle the new `approvedBy` field in the {queue} message"}

---

## Definition of Done

- [ ] Acceptance criteria above pass in all test environments
- [ ] Unit tests cover the new service method (happy path + error cases)
- [ ] Integration test covers the full request flow end-to-end
- [ ] No existing tests broken
- [ ] DB migration (if applicable) reviewed and approved by DBA
- [ ] API / MQ contract changes communicated to affected teams
- [ ] `app-manifest.yaml` updated if new endpoints, queues, or entities were added
- [ ] PR reviewed and approved by a second engineer
