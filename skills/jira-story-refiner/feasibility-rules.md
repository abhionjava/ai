# Feasibility Rules — Jira Story Refiner

Apply all 5 checks to every approach. Record ✓ Pass / ⚠ Warn / ✗ Fail with a specific reason. Any ✗ Fail = infeasible (drop it). ⚠ Warn = present with caveat.

---

## Check 1 — Stack Check

### Rules (all app types)

| Condition | Result |
|---|---|
| Approach requires a library NOT in `special_libs` (present: true) or `build` dependencies | ✗ Fail — "{library} is not in the project. Adding it requires team approval and testing." |
| Approach requires Java language features above `build.java_version` (e.g., records require 16+, sealed classes require 17+, virtual threads require 21+) | ✗ Fail — "Java {required} feature not available. Project is on Java {actual}." |
| Approach uses Spring Boot 3.x APIs but `build.spring_boot_version` is 2.x | ✗ Fail — "Spring Boot {required} API not available. Project is on {actual}." |
| Approach requires reactive programming (WebFlux, Reactor) but `api.type` is `rest` (not `rest-reactive`) | ✗ Fail — "Project uses blocking Spring MVC, not WebFlux. Reactive patterns are not compatible." |
| Approach uses Drools but `special_libs.drools` is false | ✗ Fail — "Drools is not in the project. New business rules must use inline logic or be raised as a dependency addition request." |
| Approach uses HL7 parsing but neither `hapi_hl7` nor `symphonia_hl7` is present | ✗ Fail — "No HL7 library in project. HL7 parsing cannot be implemented without adding a dependency." |

### Rules (monolith-ear only)

| Condition | Result |
|---|---|
| Approach uses Spring Boot auto-configuration, Spring Boot starters, or `@SpringBootApplication` in an EAR app | ✗ Fail — "This is a WebLogic EAR application. Spring Boot embedded server patterns are not compatible." |
| Approach introduces a REST controller using `@RestController` into the EJB module | ✗ Fail — "REST controllers belong in the web WAR module, not the EJB module." |
| Approach requires Java EE / Jakarta EE version features not available in current WebLogic version | ✗ Fail — "WebLogic {version} does not support {feature}." |

### Rules (microservice only)

| Condition | Result |
|---|---|
| Approach uses EJB patterns (`@Stateless`, `@MessageDriven`, JNDI lookups) in a Spring Boot service | ✗ Fail — "This is a Spring Boot service. EJB patterns are not applicable." |
| Approach requires a message broker not detected (e.g., Kafka when `messaging.type` is `rabbitmq`) | ✗ Fail — "{broker} is not configured in this service. Use {actual_broker} for messaging." |

---

## Check 2 — Architecture Check

### Layering rules (monolith-ear)

Permitted call directions: Web (WAR) → EJB Session Bean → JPA/JDBC → Oracle Stored Proc

| Condition | Result |
|---|---|
| Web layer directly accesses the database, bypassing the EJB layer | ✗ Fail — "Bypassing the EJB layer violates the existing architecture. Business logic must go through session beans." |
| Approach adds new business logic directly in an MDB rather than delegating to a session bean | ⚠ Warn — "MDBs should delegate to session beans for business logic. Placing logic directly in the MDB makes it harder to test and reuse." |
| New EJB session bean introduced for a single-use case without reuse potential | ⚠ Warn — "Consider whether this logic belongs in an existing session bean before creating a new one." |
| Approach modifies an EJB marked as a core integration point in `functional_context.workflows` | ⚠ Warn — "This bean is part of a core workflow ({workflow}). Changes carry regression risk across dependent flows." |

### Layering rules (microservice)

Permitted call directions: REST Controller → Service → Repository → DB

| Condition | Result |
|---|---|
| REST controller directly calls the repository, bypassing the service layer | ✗ Fail — "Bypassing the service layer violates the existing architecture. Business logic must go through the service layer." |
| Repository contains business logic beyond standard queries | ✗ Fail — "Business logic does not belong in the repository layer. Move it to the service layer." |
| Approach introduces a circular dependency between services | ✗ Fail — "Circular service dependencies will cause Spring context initialisation failures." |
| Approach adds a synchronous REST call to a downstream service within a database transaction | ⚠ Warn — "Making a remote call inside a transaction risks long-held DB locks and partial rollbacks. Consider decoupling via MQ or events." |
| Approach modifies a service listed as a core workflow in `functional_context.workflows` | ⚠ Warn — "This service is part of the core workflow '{workflow}'. Changes carry regression risk." |

---

## Check 3 — Contract Check

### API contract rules

| Condition | Result |
|---|---|
| Approach removes an existing endpoint listed in `functional_context.api_surface.rest_endpoints` | ✗ Fail — "Removing {method} {path} is a breaking change. Upstream callers listed in `upstream` will break." |
| Approach changes the request or response schema of an existing endpoint | ⚠ Warn — "Changing the schema of {method} {path} requires all upstream callers ({upstreams}) to be updated. Confirm this is coordinated before proceeding." |
| Approach adds a required field to an existing request body | ✗ Fail — "Adding a required field is a breaking change for existing callers. Make it optional or version the API." |
| Approach creates a new endpoint with a path identical to an existing one in `api_surface` | ✗ Fail — "Endpoint {method} {path} already exists. Modify the existing endpoint or choose a different path." |
| Approach adds a new endpoint that should already exist based on `functional_context.api_surface` | ⚠ Warn — "Verify {method} {path} does not already exist before implementing. Duplication risk." |

### MQ / messaging contract rules

| Condition | Result |
|---|---|
| Approach adds a new required field to an existing MQ message consumed by a downstream service | ✗ Fail — "Adding a required field to the {queue/topic} message breaks {downstream_service}. Make the field optional, or coordinate a simultaneous update with the {downstream_service} team." |
| Approach removes a field from an existing MQ message | ✗ Fail — "Removing a field from {queue/topic} may break {downstream_service} if it reads that field." |
| Approach changes the message format (e.g., JSON → XML, HL7 v2.5 → v2.6) on an existing queue | ✗ Fail — "Format change on {queue} requires coordinated update with all consumers: {downstream_services}." |
| Approach publishes to a new outbound queue not in the manifest | ⚠ Warn — "Publishing to a new queue ({queue}) requires infrastructure provisioning (WebLogic JMS module or broker config) and consumer team coordination." |
| High-volume queue affected (`volume: high` in manifest) | ⚠ Warn — "This queue is marked high-volume. Any change carries significant operational risk. Load testing required before deployment." |

---

## Check 4 — DB Check

### Rules (all app types)

| Condition | Result |
|---|---|
| Approach requires a new database table or column | ⚠ Warn — "Schema change required. {Migration detail}. Flag for DBA review and change management." |
| Approach modifies or drops an existing table or column | ⚠ Warn — "Destructive schema change. Verify no other application reads this table/column before proceeding. DBA review required." |
| Approach bypasses an existing stored procedure listed in `functional_context.stored_procedures` that enforces a business rule | ✗ Fail — "{proc_name} enforces {business_rule}. Bypassing it will violate data integrity. Either use the existing proc or update it." |
| Approach reuses an existing stored procedure from `functional_context.stored_procedures` | ✓ Pass — note "Reusing {proc_name} — no new DB artefact required." |

### Rules (monolith-ear with heavy_stored_procs: true)

| Condition | Result |
|---|---|
| Approach implements new data access logic directly in Java (JPA query or JDBC) rather than calling a stored procedure | ⚠ Warn — "This app uses heavy stored proc patterns. New data access logic is typically implemented as a stored procedure. Confirm with the DBA team whether a new proc is required." |
| Approach requires a new stored procedure | ⚠ Warn — "New Oracle stored procedure required. Raises a DBA ticket and goes through change management. Factor this into sprint planning." |

### Rules (microservice)

| Condition | Result |
|---|---|
| Approach requires a schema change but `database.migration_tool` is `none` | ✗ Fail — "No migration tool (Flyway/Liquibase) is configured. Schema changes cannot be applied in a controlled way. Add a migration tool before implementing schema changes." |
| Approach requires a new Flyway migration | ⚠ Warn — "New Flyway migration required (V{next_version}__description.sql). Ensure it is backward-compatible if the service runs in a rolling deployment." |
| Approach requires a Flyway migration that drops or renames a column | ⚠ Warn — "Destructive Flyway migration. Use a multi-phase approach: (1) add new column, (2) migrate data, (3) remove old column in a future release." |

---

## Check 5 — Cross-App Check

Verify the approach respects team ownership boundaries and the enterprise constraint that multiple applications cannot change simultaneously.

### Rules (all app types)

| Condition | Result |
|---|---|
| Approach requires changes to an application listed in `upstream` or `downstream` that is owned by another team | ⚠ Warn — "This approach requires changes to {app}, which is owned by the {team} team. Coordinate before committing to this approach. Factor in their sprint capacity." |
| Approach requires simultaneous changes to two or more applications | ✗ Fail — "Enterprise constraint: multiple applications cannot change simultaneously. Split this story into sequential tickets, one per application." |
| Approach adds a new dependency from this application to an app not currently listed in `upstream` or `downstream` | ⚠ Warn — "Introducing a new dependency on {app} expands the integration surface. Confirm this is intentional and update the manifest." |
| Story scope clearly spans more than one application | ✗ Fail — "This story touches {app_1} and {app_2}. It must be split into separate stories — one per application — before implementation can proceed." |
| Approach adds coupling to a module that is flagged as a strangler-fig extraction candidate in the manifest | ⚠ Warn — "Module {module} is an extraction candidate for the strangler-fig migration. Adding coupling here will complicate or delay the extraction. Consider whether this feature should be built directly in the target microservice instead." |
| Approach requires infrastructure changes (new queue, new DB schema, new Kubernetes config) across multiple environments | ⚠ Warn — "Infrastructure changes require DevOps coordination. Raise an infra ticket alongside this story." |
