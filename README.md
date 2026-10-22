# AWS Serverless Event Pipeline

A production-style, event-driven serverless pipeline on AWS:

**API Gateway → Lambda (ingest) → SQS → Lambda (processor) → DynamoDB**

Built the way you'd build it for real traffic: schema validation at the edge,
idempotent writes, partial batch failure handling, a dead-letter queue with
alarms, least-privilege IAM throughout, and everything defined in Terraform.
The Python code is fully covered by tests that run locally against
[moto](https://github.com/getmoto/moto) — no AWS account needed to verify
behaviour.

## Architecture

```
                        ┌──────────────────┐
  POST /events          │  Ingest Lambda   │        ┌──────────────────┐
 ─────────────────────► │  - validate body │        │ Processor Lambda │
 │ API Gateway          │  - assign event  │  SQS   │  - idempotent    │
 │ (HTTP API)           │    + correlation │ ─────► │    DynamoDB write│
 └──────────────────┘   │    IDs           │ queue  │  - partial batch │
                        │  - enqueue       │        │    failure resp. │
                        └────────┬─────────┘        └────────┬─────────┘
                                 │ 202 Accepted              │ PutItem
                                 ▼                           ▼ (conditional)
                          ┌─────────────┐            ┌──────────────────┐
                          │ CloudWatch  │            │ DynamoDB table   │
                          │ JSON logs   │            │ PK: event_id     │
                          └─────────────┘            └──────────────────┘

  Failed messages ──(maxReceiveCount = 3)──► DLQ ──► CloudWatch alarm ──► SNS
```

| Component | Choice | Why |
|---|---|---|
| Ingest API | API Gateway **HTTP API** | Cheaper and lower-latency than REST APIs; all this endpoint needs is a Lambda proxy |
| Ingest Lambda | Python 3.12, validates + enqueues, returns **202** | Keeps the synchronous path thin — downstream slowness never becomes API latency |
| Queue | SQS standard queue + **DLQ** | Decouples producers from consumers; absorbs bursts |
| Processor Lambda | SQS event source mapping, batch size 10 | Scales out automatically; `maximum_concurrency` caps it to protect downstream |
| Store | DynamoDB, `PAY_PER_REQUEST`, PK = `event_id` | Zero idle cost, and the key choice is what makes idempotency cheap (below) |

## The two design decisions that matter

### 1. Idempotency under at-least-once delivery

SQS standard queues guarantee **at-least-once** delivery: any message can
arrive twice (or more), and pretending otherwise is how duplicate orders
happen. The processor makes duplicates harmless instead of trying to prevent
them:

- The **event ID** — minted once by the ingest handler — is the DynamoDB
  partition key.
- Every write is conditional:
  `PutItem … ConditionExpression="attribute_not_exists(event_id)"`.
- If a duplicate arrives, DynamoDB rejects the write with
  `ConditionalCheckFailedException`, the processor logs *"Duplicate event
  ignored"*, and returns success — so the message is deleted and **never
  overwrites** the first write.

Exactly-once *effect*, built out of at-least-once parts. This is covered by a
dedicated test (`test_processor_duplicate_delivery_is_idempotent`) that
redelivers an event with a *different* payload and asserts the original item
is untouched.

### 2. Partial batch failures + DLQ, not all-or-nothing retries

The event source mapping enables `ReportBatchItemFailures`. The processor
returns only the message IDs that genuinely failed:

```json
{"batchItemFailures": [{"itemIdentifier": "<messageId>"}]}
```

Lambda deletes the successful messages and retries only the failures, so one
poison message can't hold a batch of ten hostage. A message that keeps
failing exhausts `maxReceiveCount` (3) and lands in the **dead-letter queue**,
where a CloudWatch alarm (`ApproximateNumberOfMessagesVisible > 0`) notifies
the SNS alerts topic. Nothing is silently dropped; after fixing the cause you
redrive the DLQ back to the main queue (an explicit redrive-allow policy is
already in place).

## Observability

- **Structured JSON logs** — both Lambdas emit one JSON object per line with
  `timestamp`, `level`, `message`, and business fields (`event_id`,
  `event_type`, …), ready for CloudWatch Logs Insights queries instead of
  regex.
- **Correlation IDs end to end** — the ingest handler honours an inbound
  `X-Correlation-Id` header (or mints one), returns it to the caller, embeds
  it in the SQS message body *and* message attributes, and the processor
  restores it into its own log context. One ID traces a single event across
  API Gateway → queue → processor → DynamoDB row.
- **Alarms on the failure modes that hurt** — DLQ depth > 0, Lambda errors
  (both functions), Lambda throttles, and oldest-message age in the main
  queue (consumer fallen behind). All route to one SNS topic with an optional
  email subscription.
- **API Gateway access logs** in JSON with request ID, route, status, and
  integration errors.

## Security

- **One IAM role per function, least privilege, no wildcard resources** —
  ingest can only `sqs:SendMessage` to the one queue and write its own log
  group; the processor can only consume that queue and `PutItem`/`GetItem`
  on the one table.
- Input is validated against an explicit allowlist schema at the edge;
  invalid events get a 400 and never enter the queue.
- SQS uses SSE, DynamoDB uses server-side encryption + point-in-time
  recovery.
- No account IDs, secrets, or real endpoints in the repo — the S3 backend
  config is placeholder-only (see `terraform/backend.tf`).

## Repository layout

```
src/            Lambda code (packaged as one zip by Terraform)
  ingest.py       API Gateway -> SQS
  processor.py    SQS -> DynamoDB
  lib/            shared logging / validation / responses / boto3 clients
tests/          pytest + moto (9 tests, all local)
events/         sample API Gateway + SQS event fixtures (used by tests)
scripts/        local_invoke.py — run the whole pipeline in-process via moto
terraform/      API Gateway, Lambdas, SQS + DLQ, DynamoDB, IAM, alarms
```

## Run it locally (no AWS account)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r tests/requirements.txt

pytest tests/ -q                 # 9 tests: validation, idempotency, partial failures…
python scripts/local_invoke.py   # ingest -> SQS -> processor -> DynamoDB, in-process
```

## Deploy

Prerequisites: an AWS account, Terraform ≥ 1.6, and a pre-created S3 bucket +
DynamoDB table for remote state.

```bash
cd terraform
cp dev.tfvars.example dev.tfvars   # adjust names/region; set alarm_email if wanted

terraform init \
  -backend-config="bucket=<your-state-bucket>" \
  -backend-config="dynamodb_table=<your-lock-table>"

terraform plan  -var-file=dev.tfvars
terraform apply -var-file=dev.tfvars
```

Then:

```bash
curl -X POST "$(terraform output -raw api_endpoint)/events" \
  -H 'Content-Type: application/json' \
  -H 'X-Correlation-Id: demo-1' \
  -d '{"type": "order.created", "source": "web",
       "data": {"order_id": "ord-1001", "amount": 42.50, "currency": "USD"}}'
# -> 202 {"status": "accepted", "event_id": "…", "correlation_id": "demo-1"}
```

## Cost notes

Everything here is pay-per-use with **no idle cost**: HTTP API charges per
request, Lambda per request + GB-seconds, SQS per request, DynamoDB
on-demand per write/read unit. A dev environment processing thousands of
events a day costs cents; an unused one costs (effectively) $0 — the only
fixed-ish charges are CloudWatch log storage, controlled by the 30-day
retention setting. That's the point of the architecture: the bill scales with
actual events, not with provisioned capacity.

## What this demonstrates

- Event-driven design with a decoupled, buffered ingest path
- **Idempotent consumers** and correct handling of at-least-once delivery
- **Partial batch responses** (`ReportBatchItemFailures`) for SQS-triggered Lambdas
- DLQ + redrive policy + alarm wiring for poison-message handling
- End-to-end **correlation IDs** and structured JSON logging
- Least-privilege, per-function IAM roles with scoped resource ARNs
- Terraform for the full stack: HTTP API, Lambda zip packaging, event source
  mapping, queues, table, log groups, alarms, SNS
- A test strategy (pytest + moto) that verifies behaviour — including failure
  paths — without an AWS account

## Notes / production hardening ideas

- The two Lambdas share one zip because their code ships together here; with
  diverging dependencies, split packaging per function or move to container
  images (`aws_lambda_function.package_type = "Image"` + ECR) — the Terraform
  is structured so that's a localised change.
- For strict ordering or built-in dedup windows, swap the standard queue for
  a **FIFO queue** — the processor's idempotency already makes that a
  belt-and-braces choice rather than a correctness requirement.
- Add an API key / JWT authorizer on the route before exposing this beyond
  trusted callers, and a WAF if it goes fully public.
