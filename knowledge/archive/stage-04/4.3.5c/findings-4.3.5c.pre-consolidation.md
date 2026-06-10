---
type: findings
stage: "4.3.5"
session: "4.3.5c"
slug: stage2-admin-ui-backfill
status: resolved
created: 2026-06-05
updated: 2026-06-05 21:24
spec: knowledge/specs/stage-04/4.3.5c-stage2-admin-ui-backfill.md
plan: knowledge/plans/stage-04/4.3.5c-stage2-admin-ui-backfill.md
report: knowledge/steps/stage-04/4.3.5c-admin-ui-final-report.md
---

# Findings - Session 4.3.5c

## Linked documents
- Spec: [[specs/stage-04/4.3.5c-stage2-admin-ui-backfill]]
- Plan: [[plans/stage-04/4.3.5c-stage2-admin-ui-backfill]]
- Report: [[4.3.5c-admin-ui-final-report]]
- ADR: [[decisions/adr-023-stage2-admin-module-membership-projection]]

## Pre-implementation evidence

### Baseline generated-client freshness
Status: fixed in current block.

Evidence:

```text
$ bash scripts/generate-api-client.sh
<no output; exit 0>

$ git diff --exit-code frontend/src/lib/api
<no output; exit 0>
```

Conclusion: generated client had no baseline drift before backend projection work began.

## Resolved findings

### F-001 - Stage 2 E2E actor email domain is rejected by create-user contract
Status: fixed in current block.

Evidence:

```text
$ set -a; . ./.env.e2e; set +a; npx playwright test tests/e2e/4.3.5c-stage2-admin.spec.ts
1 failed
POST /admin/users HTTP/1.1" 422 Unprocessable Entity
UI alert: Validation Error
```

Validation probe:

```text
$ docker compose exec backend python - <<'PY'
from app.domains.admin.schemas import CreateUserRequest
from pydantic import ValidationError
payload = {
    'email': 'owner_a_mq16k89m-9pzy81@example.test',
    'fullName': 'Owner A mq16k89m-9pzy81',
    'role': 'lecturer',
    'password': 'LocalE2EPassword123!',
    'timezone': 'UTC',
}
try:
    print(CreateUserRequest.model_validate(payload))
except ValidationError as exc:
    print(exc.errors())
PY
[{'type': 'value_error', 'loc': ('email',), 'msg': 'value is not a valid email address: The part after the @-sign is a special-use or reserved name that cannot be used with email.', 'input': 'owner_a_mq16k89m-9pzy81@example.test', 'ctx': {'reason': 'The part after the @-sign is a special-use or reserved name that cannot be used with email.'}}]
```

Backend-side EmailStr probe:

```text
$ docker compose exec backend python - <<'PY'
from pydantic import BaseModel, EmailStr, ValidationError

class Probe(BaseModel):
    email: EmailStr

candidates = [
    "probe@example.test",
    "probe@example.com",
    "probe@xyz-lms-e2e.dev",
    "probe@lms-e2e.dev",
]

for email in candidates:
    try:
        Probe(email=email)
        print(f"ACCEPTED {email}")
    except ValidationError as exc:
        print(f"REJECTED {email}: {exc.errors()[0]['msg']}")
PY
REJECTED probe@example.test: value is not a valid email address: The part after the @-sign is a special-use or reserved name that cannot be used with email.
ACCEPTED probe@example.com
ACCEPTED probe@xyz-lms-e2e.dev
ACCEPTED probe@lms-e2e.dev
```

Conclusion: the first Playwright gate used `@example.test`, but the existing backend create-user contract rejects the `.test` domain before Supabase user creation.

Root cause: E2E test data used `.test`, which backend `EmailStr` rejects.

Resolution: changed E2E actor domain to `xyz-lms-e2e.dev` after backend validation probe. No backend validation change.
