# SilverFile — 2025 Form 1040-SR draft preparation

SilverFile collects a saved interview, reads synthetic W-2 images, runs the
LangGraph agent workflow and produces a draft tax form plus reviewable audit
record. Staff resolve supported input mistakes in the dashboard. Nothing is
filed, no tax advice is given, and uncollected identity/signature details are
not invented.

## Start the dashboard

With Docker Desktop running:

```sh
git clone --branch main https://github.com/DhruvRawat418/Assignment7_taxsystem.git
cd Assignment7_taxsystem
docker compose up -d --build --wait --wait-timeout 90
```

Open **http://localhost:8501**. Configure your own OpenAI key in **Model settings**
before invoking the live AI reviewer; never commit a key. Use synthetic classroom
data only. Case databases and uploads persist in the Docker volume.

- [Docker setup and complete grader guide](README_Docker.md)
- [Detailed Docker troubleshooting](docs/DOCKER_QUICKSTART.md)
- [Local Python setup](README_TEAM.md)
- [Clean GUI scenario](demo/eval_case_1.md) and [resolved human-review scenario](demo/eval_case_2.md)
- [Staff W-2 upload, replacement and tax-form correction](docs/DOCUMENT_EDITOR.md)
- [Guardrails, coverage limits and checks](docs/GUARDRAILS.md)
- [Final integration verification](docs/FINAL_INTEGRATION_2026-10-30.md)
- [Memory experiment](docs/metrics.md)
- [AI-use attribution](docs/AI_DISCLOSURE.md)
- [Submission checklist and remaining report/video tasks](docs/SUBMISSION_CHECKLIST.md)

## Architecture

```mermaid
flowchart TD
    UI[Browser: create and resume] --> I[Intake interview: one question at a time]
    I --> DB[(SQLite checkpoints and source answers)]
    I --> S{Workflow supervisor}
    S --> IP[Intake provider: validated handoff]
    IP --> S
    S -->|Send per document| E1[Extraction worker 1]
    S -->|Send per document| E2[Extraction worker N]
    E1 --> A[Aggregation and evidence reducer]
    E2 --> A
    A --> S
    S --> R[Eligibility and Rules with citations]
    R --> S
    S --> C[Computation via deterministic MCP tools]
    C --> S
    S --> D[Audit: independent deterministic replay]
    D --> S
    S --> V[Adversarial model review]
    V -->|Findings route back to owning worker| S
    S --> H[LangGraph human-review interrupt]
    H --> U[Staff correction or stop]
    U -->|Invalidate and recheck corrected source| S
    S --> G[Bounded loop and no-progress guard]
    G --> B[Blocked or stopped: no PDF]
    S -->|Current computation and both reviews clear| F[Draft ready for human review]
    F --> P[Four-page draft PDF and audit JSON]
    S -. saved state .-> DB
```

The diagram shows allowed routes, not simultaneous execution of every stage.
Only document extraction is the genuine parallel branch. The review/revise
cycle rechecks evidence; a human action cannot simply mark stale calculations
approved. Inspect [the graph implementation](src/integration/graph.py) and tests
for routing, reducer behavior and explicit iteration/no-progress bounds.

## Contributions and submission status

Original contributor histories are retained: Hanna — Intake/memory; Xinrui —
extraction/task division; Jijuan — Rules/guardrails; Xiaolong — computation/Docker;
Yong — Audit/security/dashboard, document editor and dependent-withdrawal fix;
Dhruv — orchestration/application integration, PDF export and release verification.
The team must confirm the named specialization table in its report.

The application code is integrated. Final report, role table, video and a teammate's
fresh-machine verification remain tracked in the submission checklist. This is a
local single-operator classroom application, not a production or filing service.
