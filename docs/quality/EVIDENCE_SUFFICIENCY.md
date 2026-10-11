# Evidence sufficiency benchmark V1

## Purpose

Tropos already measures retrieval relevance:

> Did the retriever bring back the labelled knowledge?

Evidence sufficiency asks a stronger question:

> Does the eligible evidence set contain enough information to answer the query definitively using only that evidence?

These are different quality dimensions.

A retrieved passage may be relevant but still fail because critical facts are missing, coverage is partial, support conflicts materially, or the retrieved context is not actually answer-bearing. Authorization, current-version eligibility, and evidence integrity are deterministic upstream controls rather than model-judge reasons.

The first 16 evidence-set cases in this benchmark are **review candidates**, not goldens.

## Current status

| Item | Current V1 state |
| --- | --- |
| Prepared evidence-set candidates | 16 |
| Pattern families | 4 |
| Human-approved cases | 0 |
| Executable sufficiency goldens | 0 |
| Model sufficiency grader | implemented, `UNVALIDATED` |
| Production sufficiency gate | not release-valid until human calibration |

The candidate families are:

- AWS IAM / policy-layer access denial;
- Stripe webhook signature verification;
- Kubernetes / GKE out-of-memory diagnosis;
- Docker Hub pull-rate limiting.

The candidates were prepared from a multi-source public survey. Source text is paraphrased; public URLs are preserved as provenance.

## Architecture boundary

```text
query
  ↓
governed retrieval
  ↓
authorization / current-version / evidence-integrity controls
  ↓
ranked eligible Top-K evidence
  ↓
retrieval abstention V1
  ↓
immutable EvidenceSet
  ↓
EVIDENCE SUFFICIENCY
  ├── sufficient   → eligible for grounded generation
  └── insufficient → abstain / request missing evidence
  ↓
grounded generation
  ↓
artifact / answer evaluation
```

The sufficiency layer does not replace retrieval metrics.

Retrieval still measures Recall@K, ranking, expected-empty behavior, and hard invariants. Sufficiency evaluates the **complete evidence set in relation to the information need**.

## Why candidates are unlabelled

The evidence-set candidates were prepared with AI assistance from public-source research.

The repository therefore stores:

- the query;
- the paraphrased evidence set;
- pattern lineage;
- public source provenance;
- proposed split;
- stable candidate identity.

It deliberately does **not** store a proposed AI sufficiency label in the candidate file.

That prevents an AI-prepared answer key from becoming evaluation truth merely because it was committed to Git.

## Promotion lifecycle

```text
candidate
   ↓
human reviewer 1
   ↓
optional / recommended reviewer 2
   ↓
human adjudication
   ↓
approval = approved
   ↓
generic EvalDataset
```

Only `approved` cases with human review and human adjudication can project into the generic evaluation runtime.

A candidate may accumulate individual human reviews while disagreements are being resolved, but it cannot carry a final adjudication. Promotion is atomic: the final human adjudication and `approval=approved` state are committed together.

An unreviewed or partially reviewed candidate can be validated structurally, counted, versioned, and assigned to reviewers. It cannot produce a benchmark accuracy score.

## Human review contract

A review records:

| Field | Meaning |
| --- | --- |
| reviewer | Human reviewer identity |
| reviewed_at | Time of review |
| label | `SUFFICIENT` or `INSUFFICIENT` |
| reason | Why evidence is insufficient, or `NONE` |
| required_facts | Facts the reviewer believes an answer requires |
| missing_facts | Facts absent from this evidence set |
| confidence | Reviewer confidence from 1–5 |
| would_answer | Whether the evidence is sufficient to proceed |
| notes | Optional rationale / uncertainty |

### Valid sufficient review

```text
label = SUFFICIENT
reason = NONE
missing_facts = []
would_answer = true
```

### Valid insufficient review

```text
label = INSUFFICIENT
reason = one explicit insufficiency reason
would_answer = false
```

Depending on the reason, missing facts may be explicit or the failure may instead be a material conflict or lack of answer-bearing support. Authorization and version validity are handled before the judge sees an EvidenceSet.

## Reason taxonomy

| Reason | Meaning |
| --- | --- |
| `NONE` | Eligible evidence is sufficient |
| `MISSING_CRITICAL_FACT` | A specific required fact is absent |
| `PARTIAL_COVERAGE` | Some but not all of the information need is covered |
| `CONFLICTING_SUPPORT` | Eligible evidence disagrees materially on an answer-bearing fact |
| `NO_ANSWER_SUPPORT` | Evidence may be on-topic but does not support a definitive answer |
| `OTHER` | Human reviewer identifies a sufficiency gap outside the current taxonomy |

## Current candidate distribution

| Split | Candidate cases |
| --- | ---: |
| Development | 4 |
| Holdout | 4 |
| Challenge | 8 |

These split assignments are preparatory. Because this is a public repository and the labels do not yet exist, they are not blind statistical holdouts.

## Example: relevance is not sufficiency

Question:

> S3 PutObject is denied although the role has an Allow. Why?

One evidence set may contain only:

```text
The identity policy allows s3:PutObject.
```

That is relevant to the query.

It may still be insufficient because the evidence does not establish whether an SCP, permissions boundary, resource policy, session policy, or another applicable policy layer restricts the request.

A stronger evidence set may also include the explicit-deny context and the applicable policy identity.

The human reviewer decides whether those facts are enough. The retrieval score does not decide that label.

## Relationship to retrieval abstention V1

QE-109 tested a strategy-specific top-score threshold.

At the development Recall@5 floor used in that experiment, Dense MPNet improved no-answer accuracy substantially, but the frozen score-only policy still returned unsupported evidence for half of expected-empty holdout/challenge cases.

That experiment is useful because it demonstrates the boundary:

```text
retrieval score
      ≠
evidence sufficiency
```

QE-113 provides the human-labelled data needed to evaluate the next layer directly.

## Relationship to future model grading

The runtime model-based sufficiency judge receives:

```text
query + evidence set
        ↓
SUFFICIENT / INSUFFICIENT
+ reason
+ identified missing facts
```

Its output must be compared against the human-approved benchmark.

Until that calibration exists, every runtime decision carries `validation_status=UNVALIDATED`. Model output is operationally useful for the walking skeleton but is not a quality claim and will not be treated as self-validating ground truth.

## Validation controls implemented in V1

The loader enforces:

- unique case identities;
- unique evidence-set identities;
- non-empty evidence;
- unique evidence IDs within a case;
- public HTTP(S) source provenance;
- candidate vs approved state;
- reviewer identity and timezone-aware review timestamps;
- required facts for human labels;
- valid label/reason combinations;
- answer vs abstain consistency;
- approved cases require both human review and adjudication.

The generic EvalDataset projection refuses candidate cases.

## Running the validator

From `apps/api`:

```bash
uv run python scripts/validate_evidence_sufficiency_benchmark.py
```

The current expected state is:

```text
case_count      16
candidate_count 16
approved_count   0
```

That is an intentional result until human grading is returned.

## Research basis

Google Research's sufficient-context work separates cases where the model fails despite sufficient context from cases where retrieved context itself is insufficient. It also explores selective generation guided by sufficiency information.

Reference:

- Joren et al., Google Research / ICLR 2025, *Sufficient Context: A New Lens on Retrieval Augmented Generation Systems*: <https://research.google/pubs/sufficient-context-a-new-lens-on-retrieval-augmented-generation-systems/>

## Next promotion step

The next data change should come from human review, not from another AI pass.

For the prepared 16 cases:

1. reviewer 1 independently labels the case;
2. reviewer 2 labels at least a useful subset independently;
3. disagreements are adjudicated;
4. the approved labels and required/missing facts are committed as a new immutable dataset version;
5. only then does Tropos implement/evaluate a sufficiency subject or model judge.


## Human review workflow

PR #92 established the candidate/golden boundary. The operational follow-through uses spreadsheet-compatible CSV packets while keeping the JSON benchmark canonical.

The workflow is:

```text
canonical candidate JSON
        ↓
export reviewer packet
        ↓
independent human review in Excel / Sheets
        ↓
import review fields only
        ↓
reviewed candidate JSON
        ↓
agreement / disagreement report
        ↓
export adjudication packet
        ↓
human adjudication
        ↓
import adjudication
        ↓
approval = approved
        ↓
generic EvalDataset
```

Reviewer files are intentionally **not authoritative benchmark files**. Import uses only the case ID plus review fields; query, evidence, source provenance, split, and tags are reconstructed from the canonical dataset. This prevents accidental spreadsheet edits from silently mutating benchmark truth.

### Export a reviewer packet

From `apps/api`:

```bash
uv run python scripts/manage_evidence_sufficiency_reviews.py \
  export-review \
  --reviewer reviewer-1 \
  --output artifacts/evidence-sufficiency-reviewer-1.csv
```

Open the CSV in Excel or Google Sheets. For each case, complete:

- `Review Date`: ISO-8601 timestamp with timezone, for example `2026-10-11T18:30:00+05:30`;
- `Label`: `SUFFICIENT` or `INSUFFICIENT`;
- `Reason Code`: `NONE` for sufficient evidence, otherwise one reason from the taxonomy above;
- `Required Facts`: one fact per line inside the cell;
- `Missing Facts`: one fact per line when applicable;
- `Confidence`: 1–5;
- `Would you answer?`: `YES` or `NO`;
- `Notes`: optional rationale.

Do not coordinate labels between independent reviewers before both reviews are complete.

### Import a completed review

```bash
uv run python scripts/manage_evidence_sufficiency_reviews.py \
  import-review \
  --packet artifacts/evidence-sufficiency-reviewer-1.csv \
  --output artifacts/evidence-sufficiency-reviewed.json
```

Run the second reviewer against the reviewed JSON so duplicate reviewer identities are rejected while a new independent review can be appended:

```bash
uv run python scripts/manage_evidence_sufficiency_reviews.py \
  --dataset artifacts/evidence-sufficiency-reviewed.json \
  export-review \
  --reviewer reviewer-2 \
  --output artifacts/evidence-sufficiency-reviewer-2.csv
```

### Measure reviewer agreement

```bash
uv run python scripts/manage_evidence_sufficiency_reviews.py \
  --dataset artifacts/evidence-sufficiency-reviewed-twice.json \
  report
```

The report shows:

- reviewed-case coverage;
- double-reviewed-case coverage;
- observed label agreement;
- observed label+reason agreement;
- explicit disagreement case IDs;
- low-confidence case IDs.

With only 16 seed cases, observed agreement is reported directly rather than presenting a more elaborate statistic as more stable than the sample warrants.

### Adjudicate and promote

After review, export an adjudication packet:

```bash
uv run python scripts/manage_evidence_sufficiency_reviews.py \
  --dataset artifacts/evidence-sufficiency-reviewed-twice.json \
  export-adjudication \
  --output artifacts/evidence-sufficiency-adjudication.csv
```

The adjudicator reviews the independent decisions and fills the final label, reason, required/missing facts, confidence, answer/abstain decision, identity, timestamp, and notes.

Import the completed adjudication:

```bash
uv run python scripts/manage_evidence_sufficiency_reviews.py \
  --dataset artifacts/evidence-sufficiency-reviewed-twice.json \
  import-adjudication \
  --packet artifacts/evidence-sufficiency-adjudication.csv \
  --output artifacts/evidence-sufficiency-approved-v1.json
```

Promotion is atomic per completed case: the case receives the human adjudication and changes to `approval=approved` together. Blank adjudication rows remain candidates. Approved cases can then project into the generic evaluation runtime; partially reviewed cases still cannot.
