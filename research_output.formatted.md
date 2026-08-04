# Research Notes

Generated At: 2026-08-04 15:02:14

## 1) Company and role context overview (evidence-oriented)

### What the company does (from provided URLs)
- **URL-derived fact:** One provided link is `https://bjak.my/en`, which is the primary company domain for **BJAK**.
- **Inference (not verified in-page here):** BJAK appears to be a consumer-facing financial/insurance technology company in Southeast Asia (commonly associated with insurance comparison/distribution).
- **URL-derived fact:** Another link is a Built In posting URL: `https://builtin.com/job/founding-ai-engineer/7869823`, indicating a **Founding AI Engineer** listing exists/existed at that path.

### Role summary from URLs
- **Role summary from URLs: partially available / mismatched.**
  - The Built In URL path references **“founding-ai-engineer”**, not explicitly **Graph Data Engineer / SPARQL Developer**.
  - Because of this mismatch, detailed role scope for the target role is **not reliably available from URLs alone**.

### Fallback role summary (from Job Spec)
- Build APIs using **SPARQL + Python**.
- Work with **RDF/OWL/semantic web** and graph databases (**Stardog/Neo4j**).
- Use **SQL, Python, JavaScript** for processing/visualization.
- Domain focus: **telecom network architecture**, **Service Fulfilment (Provisioning/Activation)**, **OSS/BSS**, **CMDB/network inventory**, and **event-driven real-time architectures** (Kafka, REST).


## 2) Role-specific insights that matter to this candidate

- **Primary gap:** CV is strong in mobile/platform engineering, but lacks explicit **SPARQL/RDF/OWL** and **telecom OSS/BSS** delivery examples.
- **Transferable strengths:** Strong **Python, SQL, API design, data tooling automation, cross-system integration**, and customer-facing delivery.
- **Interview risk:** Team may question immediate effectiveness in semantic graph modeling and telecom fulfillment workflows.
- **Best positioning:** Present as a senior systems engineer who can ramp quickly on graph semantics, with proven success in new domains and production hardening.


## 3) Targeted interview questions (with exemplar answers, research topics, prior-role evidence)

### Theme A — Semantic web / graph fundamentals

1) **How would you model telecom inventory in RDF for querying service activation readiness?**
**Why useful:** Tests core fit to RDF/SPARQL + telecom domain.
**Exemplar answer:** “Model entities as classes (device, port, service, customer endpoint), define relationships for topology and dependencies, and keep lifecycle state as typed properties. Use named graphs for source/system boundaries and provenance.”
**Research next:** RDF schema design patterns, SHACL validation, telecom SID alignment.
**Relevant CV roles:** RMS Services (asset discovery/data modeling), This One (schema + backend design).

2) **What SPARQL query patterns would you use for path/dependency traversal?**
**Why useful:** Assesses practical SPARQL depth.
**Exemplar answer:** “Use property paths for multi-hop traversal, optional blocks for sparse metadata, and subqueries for staged filtering. Add pagination and bounded traversals to control runtime.”
**Research next:** SPARQL 1.1 property paths, query optimization on Stardog/Neo4j adapters.
**Relevant CV roles:** MySpace middleware, Boostworks API/data automation.

3) **How do OWL ontologies help beyond plain graph storage?**
**Why useful:** Distinguishes ontology engineering from simple graph DB use.
**Exemplar answer:** “OWL enables formal semantics and inference (class hierarchy, equivalence, constraints) so downstream apps can reason over implicit facts, not only explicit edges.”
**Research next:** OWL profiles (EL/QL/RL), reasoning cost trade-offs.
**Relevant CV roles:** Cross-platform architecture leadership (conceptual modeling strength), AI degree foundation.


### Theme B — API and data architecture

4) **Design an API layer that exposes SPARQL safely to downstream systems.**
**Why useful:** Directly maps to role responsibility.
**Exemplar answer:** “Expose task-oriented REST endpoints backed by parameterized SPARQL templates, enforce authz per graph scope, validate inputs, and add caching for stable read paths.”
**Research next:** SPARQL injection defenses, API gateway policy, observability for query latency.
**Relevant CV roles:** Boostworks (OpenAPI pipelines), This One (Flask mock/backend).

5) **How would you handle near-real-time graph updates from Kafka events?**
**Why useful:** Validates event-driven integration capability.
**Exemplar answer:** “Use an ingest service to normalize events, enforce idempotency keys, and apply upserts to graph triples with replay-safe offsets. Track DLQ handling and consistency SLAs.”
**Research next:** Kafka exactly-once semantics limits, CDC-to-graph patterns.
**Relevant CV roles:** Large-scale CI/CD and automation at Boostworks; middleware experience at MySpace.

6) **How would you balance SQL stores and graph stores in one architecture?**
**Why useful:** Tests polyglot persistence judgment.
**Exemplar answer:** “Use SQL for transactional/reporting workloads and graph for relationship-heavy traversal/inference. Maintain contract-defined synchronization with lineage and freshness metrics.”
**Research next:** Data product boundaries, eventual consistency playbooks.
**Relevant CV roles:** Python + PostgreSQL history, backend integration roles.


### Theme C — Telecom domain application

7) **What data is critical for provisioning/activation decisions in OSS/BSS flows?**
**Why useful:** Checks domain readiness.
**Exemplar answer:** “Service intent, inventory availability, topology constraints, compatibility rules, and current operational state/events. Activation should be policy-gated and auditable.”
**Research next:** OSS/BSS order-to-activate lifecycle, TM Forum concepts.
**Relevant CV roles:** QoS/network analytics history (Actual Experience), low-level network work.

8) **How would you integrate CMDB and network inventory with graph ontology?**
**Why useful:** Core requirement in spec.
**Exemplar answer:** “Map CMDB CIs and inventory objects into ontology classes, preserve source IDs for traceability, and reconcile conflicts using source-priority and timestamp rules.”
**Research next:** CI reconciliation strategies, canonical model governance.
**Relevant CV roles:** Asset discovery at RMS; enterprise integration at Dyson/Boostworks.


### Theme D — Delivery, collaboration, customer communication

9) **A customer reports slow activation decisions; how do you troubleshoot?**
**Why useful:** Tests production ownership and communication.
**Exemplar answer:** “Segment by data freshness, query performance, and downstream API latency. Provide incident timeline, short-term mitigation, and measurable remediation plan.”
**Research next:** Graph query profiling in Stardog/Neo4j, SLO design.
**Relevant CV roles:** Bugsnag support, Boostworks client-facing ownership.

10) **How do you lead when domain expertise is initially incomplete?**
**Why useful:** Evaluates ramp strategy for career-pivot profile.
**Exemplar answer:** “Define a 30/60/90 learning-delivery plan: ontology spike, one production API slice, then reliability hardening; pair weekly with domain SMEs and publish decision logs.”
**Research next:** Telecom glossary build-out, sample OSS/BSS integration case studies.
**Relevant CV roles:** Multiple rapid ramp-ups in contract/startup environments.


## 4) Why these questions are useful (summary)

- They directly test the job’s hard requirements: **SPARQL/RDF/OWL, graph DBs, telecom workflows, event-driven APIs**.
- They expose readiness for a likely concern: **domain and semantic-web depth vs strong general engineering seniority**.
- They let the candidate demonstrate **transferable production leadership** despite non-linear background.


## 5) Questions the candidate should ask the company (grouped by theme, with fit + follow-ups)

### Theme A — Role scope and success criteria
1) **“In the first 90 days, what production outcomes define success for this role?”**
Why this demonstrates fit: Shows delivery focus and onboarding discipline.
Follow-ups:
- “Is success measured by API throughput/latency, data quality, or provisioning accuracy?”
- “Which milestone is highest risk today?”

2) **“How much of the role is ontology design vs API/data engineering?”**
Why this demonstrates fit: Aligns skill depth with day-to-day expectations.
Follow-ups:
- “Who owns ontology governance decisions?”
- “Are reasoning rules already established or still evolving?”

### Theme B — Data/platform architecture
3) **“Which graph stack is live today (Stardog, Neo4j, hybrid), and what are current bottlenecks?”**
Why this demonstrates fit: Signals practical platform thinking.
Follow-ups:
- “Where do you see most latency: ingest, query, or inference?”
- “What observability exists for SPARQL performance?”

4) **“How are Kafka events normalized before graph ingestion?”**
Why this demonstrates fit: Connects event architecture to data reliability.
Follow-ups:
- “How are duplicates and out-of-order events handled?”
- “Is there a dead-letter queue replay process?”

### Theme C — Telecom domain and integration
5) **“Which OSS/BSS and CMDB systems are in scope for integration first?”**
Why this demonstrates fit: Targets integration sequencing and complexity.
Follow-ups:
- “Is there a canonical model already defined?”
- “What is the current reconciliation strategy across systems?”

6) **“How is provisioning/activation policy represented today—code, rules engine, or ontology?”**
Why this demonstrates fit: Probes decisioning architecture maturity.
Follow-ups:
- “Who signs off on policy changes?”
- “How is auditability handled for activation decisions?”

### Theme D — Team and customer interaction
7) **“How customer-facing is this role during incident analysis or solution design?”**
Why this demonstrates fit: Matches strong stakeholder communication background.
Follow-ups:
- “Will this role join customer technical workshops?”
- “What communication cadence is expected during incidents?”

8) **“What domain upskilling support exists for telecom semantics (documents, SMEs, sandbox data)?”**
Why this demonstrates fit: Shows proactive ramp planning.
Follow-ups:
- “Can I pair with a telecom architect in the first month?”
- “Are there internal ontology standards I should follow?”


## 6) Follow-up points for candidate questions
- Included above under each question as **follow-ups** for live discussion steering.


## 7) Candidate revision focus (before interview)

- Prepare a **clear transition narrative**: mobile principal engineer → graph/API engineer with deep integration and reliability experience.
- Build 2–3 **SPARQL examples** (joins, traversal, aggregation, filtering) and be ready to explain performance considerations.
- Create a concise **telecom primer**: OSS/BSS flow, CMDB linkage, provisioning vs activation distinction.
- Map CV stories to role needs:
  - **Boostworks:** API automation, scale, client communication.
  - **RMS/MySpace:** backend/data/middleware credibility.
  - **Bugsnag/Dyson:** production support, security, enterprise rigor.
- Be explicit about **learning plan** for RDF/OWL/EXFO PRONTO.


## 8) Brief glossary (role-relevant, concise)

- **SPARQL (SPARQL Protocol and RDF Query Language):** Query language for graph data in RDF; candidate should relate to SQL fluency and API work.
- **RDF (Resource Description Framework):** Triple-based data model (subject-predicate-object) for linked data; similar to candidate’s schema/integration work.
- **OWL (Web Ontology Language):** Semantic modeling language enabling inference over RDF data; relevant to architecture strengths but likely new tool depth.
- **Ontology:** Formal domain model of entities/relations/rules; comparable to domain-driven modeling the candidate has done in backend/mobile systems.
- **Stardog:** Enterprise graph database/knowledge graph platform supporting SPARQL and reasoning; likely a target stack to upskill.
- **Neo4j:** Graph database commonly using Cypher (and integrations); relevant if team uses mixed graph tooling.
- **OSS/BSS (Operations Support Systems / Business Support Systems):** Telecom operational + commercial systems that drive service lifecycle.
- **CMDB (Configuration Management Database):** System of record for configuration items and relationships; maps naturally into graph structures.
- **Provisioning vs Activation:** Provisioning allocates/configures resources; activation turns service on for use/billing.
- **EXFO PRONTO:** Telecom-focused ontology/model reference mentioned in spec; candidate should request internal schema examples early.
- **Kafka:** Distributed event streaming platform for real-time pipelines; candidate can connect to prior middleware/automation patterns.


## 9) Risk and uncertainty notes

- **High uncertainty:** Live content of both URLs could not be fully verified here; Built In slug suggests a different role (**Founding AI Engineer**) than provided spec.
- **Likely mismatch risk:** Company name is listed as “New company,” while one URL points to BJAK; confirm legal entity and hiring team.
- **Action:** Validate exact role posting, reporting line, stack (Stardog vs Neo4j), and telecom domain expectations in recruiter screen.
