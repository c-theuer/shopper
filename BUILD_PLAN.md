# AI Shopping Assistant: Build Plan

Source: [AI Shopping Assistant PRD](https://docs.google.com/document/d/1OZ9wW5uGahWtGlzvbe6lg0rpew4Cyqpw/edit) (Draft)
GCP project: set by the `project_id` Terraform variable and the `PROJECT_ID` deploy variable (see `infra/README.md`)

## Current state: clickable demo

The repo currently holds a **demo** built to show the experience is possible, not the production MVP below.

- **Mock merchants.** Six stores (0.8 to 12.4 mi from the Ferry Building, San Francisco) and about 35 products are seeded in `backend/app/seed.py`. Nothing is really bought.
- **Cards: demo only, not PCI compliant.** Card details are stored in plain text. To make that safe, `backend/app/cards.py` accepts only published test card numbers (such as 4242 4242 4242 4242) and rejects everything else. The CVC is never stored, and the API only returns brand and last 4. **Never put real cards into this system.** Production still needs the tokenization decision in section 6.
- **Wallet: demo only, no real bank.** In Settings the user chooses whether the agent pays with the test card or the wallet. The wallet is funded from a linked bank account, but `backend/app/bank.py` accepts only the published test routing number 110000000 with test account numbers (such as 000123456789), and only the last 4 digits are stored. Deposits are instant. The balance is the sum of an append-only ledger (`wallet_entries`: deposits, purchases, refunds). If the balance can't cover a cart, the guardrail engine defers it (`insufficient_funds`) and the Inbox gets one "add funds" notice. Canceling a wallet order refunds the wallet but not the weekly allowance. Production would need a bank or banking-as-a-service partner, real ACH with settlement delays and returns, KYC, and a licensing review for holding customer funds (money transmission).
- **Agent.** Claude (`claude-opus-5-5`) handles clarifying questions and product choice when `ANTHROPIC_API_KEY` is set. Otherwise it falls back to keyword rules. `backend/app/guardrails.py` makes every purchase decision.
- **Voice.** A "Talk to Shopper" panel uses Chrome's built-in Web Speech API: Chrome transcribes speech (through Google's speech service) and reads replies aloud, and other browsers get a text box instead. `POST /api/voice` has Claude, or keyword rules without a key, turn the words into one of four actions: add items, remove items, answer the agent's question, or read the list. Voice can't approve orders, move money, or change settings. After the agent asks a question, the mic reopens for the answer.
- **Demo clock.** A demo bar lets you set or jump the time, run shopping, send the daily summary and reset to the "Mike" persona.
- **Notifications** go to an in-app Inbox; nothing is emailed or texted.
- **How the PRD's limit conflicts are resolved:**
  - Blocked: orders over $1,000, or weekly spend over $15,000.
  - Needs approval: orders over $100, or going past $300 in a calendar day.
  - Deferred: a 4th order within an hour.
- **Carts.** Items are grouped into one cart per store. An approval covers one exact cart, and any change to it invalidates the approval.
- **Not built yet:** weekly rollover of recurring items, real merchant integrations, real notification sending, and Alembic migrations (tables are created at startup).

Run it locally with `docker compose up --build` and open http://localhost:8080. Tests: `cd backend && uv run pytest` (needs the compose Postgres on port 5433).

## 1. MVP decisions already made (from the PRD)

- Delivery only, no pickup.
- The app is a web page.
- One user account. No auth system is built. IAP in front of the web app handles Google sign-in.
- Stripe is dropped. How cards are stored and charged is open (see section 6, item 1). Raw card numbers must not reach our database.
- All medicines are blocked.
- USD only. A week runs Monday 00:00 to Sunday 23:59 in the user's timezone.
- Distance is the straight-line radius (10 mi) from the configured location to the store that fulfills the order.
- Refunds do not replenish the weekly allowance.
- Unfinished items roll into the next week. Completed one-time items do not.

## 2. Architecture

| Concern | Choice | Why |
| --- | --- | --- |
| Frontend | TypeScript + React (Vite), served by a small Node server that proxies `/api` to the backend | A single web page app |
| Backend | Python FastAPI | Guardrail engine, planner, commit pipeline, jobs |
| Hosting | Two Cloud Run services, both Docker containers. The frontend sits behind IAP. The backend has internal-only ingress and only the frontend can invoke it | Fits the existing GCP project and scales to zero |
| Infra as code | Terraform in `infra/terraform` | See `infra/README.md` |
| Database | Postgres on Cloud SQL | Row locks and transactions are needed for budget reservations and duplicate prevention |
| Jobs | Cloud Scheduler hitting authenticated internal endpoints (shopping tick every 5 min, daily summary at 17:05 local, weekly rollover) | Simple and fits the time windows |
| Secrets | Secret Manager | Database password, payment provider and notification provider keys |
| Payments | To be decided: a tokenization vault or processor behind a `PaymentProvider` interface, with a mock for the MVP | Keeps raw card numbers out of our database (see section 6) |
| Notifications | Email (Resend or SendGrid) and SMS (Twilio) behind a `Notifier` interface | Swappable, and easy to mock |
| Agent / LLM | Claude, used for item clarification, product matching, and plain-language explanations | Never makes guardrail decisions |
| Merchants | A `MerchantAdapter` interface with a mock merchant for the MVP | Real merchants are still undecided (see section 6) |

**Core principle: the LLM proposes and deterministic code decides.** Every spend, distance, time, category, and approval check runs in a pure Python guardrail engine. The LLM never sees payment credentials and cannot place an order.

### Order commit pipeline (the heart of the system)

```
candidate cart (from planner)
  -> BEGIN tx; SELECT user FOR UPDATE
  -> reload list items, compare list_version against the cart snapshot  (FR3)
  -> compute total = items + tax + delivery + service fees - discounts   (FR5)
  -> guardrail engine: platform rules -> user rules -> approval check    (§5)
  -> insert order(status=RESERVED, idempotency_key), reserve the amount
  -> COMMIT
  -> merchant.submit(idempotency_key)        <- purchase commitment point
  -> payment_provider.charge(token, idempotency_key)
  -> order -> PLACED | FAILED | UNKNOWN
  -> UNKNOWN goes to the reconciler, which never retries blindly
```

## 3. Data model (first pass)

- `user_settings`: location (lat/lng), timezone, shopping enabled/paused, user caps (weekly budget, per-order limit, max delivery fee), permitted days, categories that always need approval, substitution default, notification channels and verified contacts, payment token reference (never a raw card number).
- `list_items`: name, category, quantity, specs (JSON), max price, substitution preference, priority, needed-by date, recurrence, notes, status, `version`, soft-delete.
- `list_events`: an append-only log of every add, edit, and remove (audit trail, FR9).
- `stores`: merchant, store ID, lat/lng, verified flag.
- `orders`: merchant, store, line items snapshot, cost breakdown, total, status (RESERVED, SUBMITTED, PLACED, FAILED, UNKNOWN, CANCELED), idempotency key, payment reference, the list versions it was built from, committed_at, delivery status.
- `approvals`: order snapshot hash, the exception rule(s) being exceeded, effect on budget, alternatives, expires_at, status (PENDING, APPROVED, REJECTED, EXPIRED, INVALIDATED).
- `guardrail_decisions`: every evaluation with its rule results (including blocks), for audit.
- `notifications`: type, channel, payload, delivery status.

## 4. Phases

Each phase ends with something you can demo. Phases 3 and 4 can run in parallel once phase 2 lands.

### Phase 0: Foundation (scaffold done)
- Done: React + Vite frontend with a Node proxy, FastAPI backend, Dockerfiles, `docker-compose.yml`, Terraform (VPC, Cloud SQL private IP, Artifact Registry, Secret Manager, two Cloud Run services, IAP), and `scripts/deploy.sh`.
- To do: SQLAlchemy models with Alembic migrations, pytest, Vitest, Playwright, and CI (lint, typecheck, and tests on every push).

**Done when:** `scripts/deploy.sh` runs and the deployed page shows "backend ok, database reachable".

### Phase 1: Setup and shopping list (FR1, FR2)
- Settings page: location (address to lat/lng), timezone, budgets and preferences, notification channels with email/SMS verification codes.
- Card capture through the chosen provider's hosted fields, so card numbers never touch our servers. Store only the token. Use a mock provider until the choice is made.
- A page explaining the fixed platform restrictions (journey stage 1).
- List UI: add, edit, remove, and defer items with all FR2 fields. Status badges. Every change bumps `version` and writes a `list_events` row.
- Enable, pause, and resume toggle. Shopping stays disabled until setup is complete.
- Accessibility pass on list, approval, and pause controls (keyboard and screen reader).

**Done when:** acceptance criterion 1 passes and a (mock) payment token is saved.

### Phase 2: Guardrail engine (section 5, FR4, FR5)
A pure function: `evaluate(order, context) -> Decision(ALLOW | NEEDS_APPROVAL | BLOCK, reasons)`

Platform rules (never overridable):
- Order total over $1,000.00 is blocked.
- Weekly committed + reserved + this order over $15,000 is blocked.
- Fulfilling store over 10 mi, or not verified, is blocked.
- Commit time outside [10:00, 17:00) local is blocked (deferred, not failed).
- Credit card bills, EMIs, installment or BNPL plans, and any medicine are blocked.
- Unbounded or unconfirmed final charges are blocked.
- Paused shopping is blocked.
- Velocity and micro-cap rules (pending the confirmation in section 6): orders over $100 need confirmation, at most 3 automated orders per rolling 60 min, and $300 per day.

User rules (approval possible): per-order limit, weekly budget, item max price, brand/store/spec mismatch, substitution, delivery fee, permitted day, categories that always need approval.

Category blocking runs in two layers: a deterministic keyword and category list first, then an LLM classifier that can only make things stricter (it can add a block, never remove one).

Also: cart-splitting detection, so items from one list request can't be split across orders to dodge a cap.

**Done when:** a table-driven test suite covers every row of PRD section 8 and acceptance criteria 3 to 9, at boundaries ($100.00 vs $100.01, $1,000.00 vs $1,000.01, 16:59:59 vs 17:00:00, 10.0 mi vs 10.01 mi, DST change days).

### Phase 3: Merchants, stores, and product selection (FR4)
- `MerchantAdapter`: `searchStores(location)`, `searchProducts(store, query)`, `quote(cart)` (final total with tax and fees), `submit(cart, idempotencyKey)`, `getOrder(id)`, `cancel(id)`.
- A mock merchant with seeded stores at 3, 9, and 12 mi, varied prices, out-of-stock items, and fault injection (timeouts, ambiguous responses).
- Store eligibility: haversine distance from the user location to the fulfilling store.

**Done when:** you can search the mock merchant from a list item and only stores within 10 mi come back.

### Phase 4: Agent planner (journey stages 3 to 5)
- When an item is saved, Claude checks it for missing info (size, brand, type) and sets the status to Needs clarification with a specific question (the Mike persona flow).
- Planner: for each Ready item, search eligible stores, rank compliant candidates on spec match and total cost, and apply substitution rules. Outputs candidate carts with a snapshot of the list versions they were built from.
- Research may run any time. Only commits are restricted to the window.
- Use structured outputs and tool use. The LLM gets product data, never payment data.

**Done when:** the PRD's "daily list update" example (milk, lamp, chair) produces the right candidate carts.

### Phase 5: Commit pipeline and reconciliation (FR3, FR5, NFR reliability)
- Implement the pipeline in section 2 with a single-writer lock per user.
- Reservations count toward weekly and daily caps while in flight. Funds are released only after a confirmed failure.
- Idempotency keys are shared by the merchant and payment calls.
- Reconciler job: for UNKNOWN orders, query the merchant by idempotency key, then settle the order as PLACED or FAILED. It never resubmits without a confirmed failure.
- Edits after the commitment point: show "already ordered" plus cancel or return options. Never imply an order was canceled.

**Done when:** acceptance criteria 2, 4, and 12 pass, including a concurrency test (parallel commits can't overspend) and a fault injection test (a merchant timeout creates no duplicate order).

### Phase 6: Approval workflow (FR6, section 12)
- An approval card shows the exact items, merchant, total, the rule exceeded, the budget impact, alternatives, and when it expires.
- Actions: Approve once, Reject, Edit item, Update preferences.
- An approval is tied to the order snapshot hash. Any change to price, product, quantity, merchant, or relevant list fields marks it INVALIDATED.
- Expired or unanswered approvals become BLOCKED (fail closed).
- An approval outside the window waits for the next window, then the full guardrail check runs again.

**Done when:** acceptance criteria 7 and 8 pass, plus the section 8 rows "edit while awaiting approval" and "approval at 5:15 p.m."

### Phase 7: Scheduling and pause (FR7)
- Shopping tick every 5 minutes. It runs the planner and commit pipeline for users whose local time is in the window and who are not paused.
- Pause takes effect immediately. The commit pipeline rechecks the pause flag inside the transaction.
- Weekly rollover job: reset the window, roll over unfinished items, and clear completed one-time items.

**Done when:** acceptance criteria 6 and 11 pass.

### Phase 8: Notifications and daily summary (FR8)
- Daily summary at 17:05 local: purchases and merchants, today's spend, weekly spend and what's left, unpurchased/unavailable/blocked items, pending approvals, order status, and receipt links.
- Optional per-purchase notification after a confirmed PLACED order.
- Sends go through an outbox table, so a notification failure never re-triggers a purchase.
- Approval requests always send, whatever the notification settings.

**Done when:** acceptance criterion 10 passes.

### Phase 9: History and audit (FR9)
- History page: orders, line items, receipts, actual charges, approval decisions, list changes, and blocked attempts with their reasons.
- A redaction check so no card data appears in logs, summaries, or notifications (only token references and the last 4 digits, if anything).

### Phase 10: Hardening and pilot readiness
- An end-to-end Playwright suite mapped one to one to the 12 acceptance criteria.
- Outage recovery test: kill the service mid-commit, restart, and confirm the reconciler settles the order.
- Daily Cloud SQL backups, structured logging, and alerts on UNKNOWN orders and guardrail blocks.
- Pilot metrics: auto-purchase rate, unwanted purchases, summary delivery rate.

## 5. Acceptance criteria traceability

| # | Criterion | Phase | Test type |
| --- | --- | --- | --- |
| 1 | Weekly list with daily add, edit, remove | 1 | E2E |
| 2 | Purchases use the latest list at the commitment point | 5 | Integration |
| 3 | Orders over $1,000 blocked, fees included | 2 | Unit (boundaries) |
| 4 | Weekly spend never over $15,000, even with simultaneous orders | 2, 5 | Unit + concurrency |
| 5 | Only stores within 10 mi | 2, 3 | Unit + integration |
| 6 | Orders only in the local-time window | 2, 7 | Unit (time-mocked) |
| 7 | Exceptions need a valid approval | 6 | Integration |
| 8 | Platform rules still enforced after approval | 2, 6 | Integration |
| 9 | Card bills, EMIs, and medicine blocked | 2 | Unit |
| 10 | Daily summary and optional notifications | 8 | Integration |
| 11 | Pause stops new purchases | 7 | Integration |
| 12 | Uncertain merchant responses reconciled with no duplicates | 5 | Fault injection |

## 6. Open questions to resolve before or during the build

1. **Card storage and money flow (blocks real purchases, not phases 0 to 4).** With Stripe dropped, pick a tokenization vault or processor so raw card numbers never touch our servers. Storing them ourselves puts the whole system in full PCI DSS scope. We also still need a way to pay the store: charging the user ourselves makes the platform the merchant of record. ("Bank Transaction Policies" in PRD section 12 is unfinished.)
2. **Spending tiers conflict.** Section 5 adds a $100 auto-approve micro-cap, 3 orders per 60 minutes, and a $300 per day cap "without 2FA". Those limit a week to about $2,100 without 2FA, which makes the $15,000 weekly cap close to unreachable. Confirm which rules are platform rules and what "2FA re-authentication" means with no auth in the MVP. This plan treats them as platform rules, with the web approval card standing in for the "1-tap mobile push".
3. **Daily cap wording.** Section 5 says a *rolling* $300 per day. FR5 says a *calendar* day. Pick one.
4. **Approval authentication.** Mostly covered by IAP: approving happens in the web app behind Google sign-in. Links in email or SMS should open the app, never approve directly from the link.
5. **Pilot merchants.** Which real merchant(s) have reliable final pricing, checkout, and order-status APIs? The mock merchant covers everything until this is decided.
6. **Approval expiry duration.** It isn't specified. Proposal: the end of the current shopping window, or 4 hours, whichever comes first.
7. **Duplicate section numbering in the PRD** (two sections numbered 7). Cosmetic.
