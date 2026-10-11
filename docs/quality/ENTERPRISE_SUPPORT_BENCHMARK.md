# Enterprise support benchmark V1

## Purpose

This benchmark replaces toy retrieval examples with complete, realistic synthetic support cases that can exercise three Tropos product boundaries from one case record:

1. retrieval of existing governed knowledge;
2. the Resolve decision to `REUSE`, `IMPROVE`, `CREATE`, or `NO_ACTION`;
3. grounded Knowledge Article generation when knowledge must be created or improved.

The dataset is a **development-quality evidence seed**, not a production accuracy benchmark. It is intentionally richer before it is large.

## Why complete cases

A retrieval-only row such as `query → relevant document` is insufficient to evaluate the product Tropos is trying to build. The actual workflow starts with a resolved support interaction.

A benchmark case therefore preserves the operational context that drives the knowledge decision:

```text
case description
+ comments
+ work notes / diagnostics
+ environment
+ resolution notes
        ↓
closure evidence
        ↓
retrieve existing knowledge
        ↓
REUSE / IMPROVE / CREATE / NO_ACTION
        ↓
grounded Knowledge Article expectation
  when CREATE or IMPROVE applies
```

The case shape is intentionally similar to real service-management records. ServiceNow's current knowledge-generation documentation identifies short description, description, resolution notes, work notes, and comments as case inputs used to draft knowledge. KCS likewise emphasizes capturing requestor context in the workflow, linking a relevant article when one exists, improving it with additional context where needed, and creating a new article only when no relevant article exists.

## Research basis

The committed records are synthetic. Public vendor documentation is used only to identify realistic failure patterns, diagnostic distinctions, and workflow shapes; vendor/customer text is not copied into the benchmark.

| Pattern ID | Public pattern used |
| --- | --- |
| `ms-ca-errors` | Microsoft Entra Conditional Access error distinctions such as device noncompliance, domain-join, approved-app, and policy-block failures |
| `ms-intune-ca` | Intune Conditional Access troubleshooting, including compliance refresh and device-state propagation |
| `ms-ca-lockout` | Conditional Access configurations that can lock administrators out and the need for emergency-access exclusions |
| `ms-intune-enrollment` | Intune enrollment failures including device-cap and Company Portal failure modes |
| `ms-ade-ca` | Automated Device Enrollment devices that require the Company Portal registration path for Conditional Access |
| `aws-access-denied` | AWS IAM access-denied analysis across identity policies, explicit denies, permissions boundaries, and other policy layers |
| `atlassian-request-visibility` | Jira Service Management portal visibility requirements such as request type, portal access, reporter/participant relationship, and issue security |
| `atlassian-security-level` | Request invisibility caused by issue-security configuration |
| `atlassian-email-request-type` | Email-channel request types requiring summary/description with additional visible fields kept optional |
| `kcs-capture` | KCS capture/reuse/improve/create discipline and the requirement for enough closure context to create reusable knowledge |
| `servicenow-case-knowledge` | Drafting knowledge from resolved/closed cases and requiring agent review before publication |

Public references:

- Microsoft: <https://learn.microsoft.com/en-us/entra/identity/conditional-access/troubleshoot-conditional-access>
- Microsoft: <https://learn.microsoft.com/en-us/troubleshoot/mem/intune/device-protection/troubleshoot-conditional-access>
- Microsoft: <https://learn.microsoft.com/en-us/troubleshoot/mem/intune/device-enrollment/troubleshoot-device-enrollment-in-intune>
- Microsoft: <https://learn.microsoft.com/en-us/troubleshoot/mem/intune/device-protection/cannot-access-company-resources-on-dep>
- AWS: <https://docs.aws.amazon.com/IAM/latest/UserGuide/troubleshoot_access-denied.html>
- Atlassian: <https://support.atlassian.com/jira/kb/a-request-cant-be-viewed-from-the-customer-portal-in-jsm/>
- Atlassian: <https://support.atlassian.com/jira/kb/no-suitable-request-type-for-the-email-channel-error-in-jira-service/>
- KCS: <https://library.serviceinnovation.org/KCS/Knowledge-Centered_Success_Practices_Guide/201-Solve_Loop/Practice_1_Reuse/Technique_1.3>
- KCS: <https://library.serviceinnovation.org/KCS/Knowledge-Centered_Success_Practices_Guide/201-Solve_Loop/Practice_3_Capture/Technique_3.4>
- ServiceNow: <https://www.servicenow.com/docs/r/customer-service-management/now-assist-for-csm/configure-knowledge-generation-in-now-assist_0.html>
- ServiceNow: <https://www.servicenow.com/docs/r/customer-service-management/now-assist-for-csm/Now-Assist-generate-article-csm-workspace.html>

## Dataset contents

The canonical file is:

`apps/api/evals/resolve/enterprise_support_benchmark_v1.json`

Current V1 contains:

| Evidence | Count |
| --- | ---: |
| Synthetic knowledge documents | 18 |
| Complete resolved support cases | 16 |
| REUSE cases | 4 |
| IMPROVE cases | 4 |
| CREATE cases | 4 |
| NO_ACTION cases | 4 |
| Grounded Knowledge Article expectations | 8 |
| Retrieval queries | 48 |
| Answerable retrieval queries | 24 |
| Expected-empty retrieval queries | 24 |

The support cases cover three intentionally coherent enterprise-support areas:

- Microsoft Entra / Intune identity and endpoint access;
- AWS IAM and cloud authorization;
- Jira Service Management request and portal behavior.

The corpus also contains near-distractors and restricted administrative material so retrieval is not reduced to matching a unique topic word.

## Case structure

Each case contains:

```text
case_id
split
approval / origin
research-pattern lineage
access context
case_record
├── status / priority / channel
├── opened / resolved timestamps
├── short description
├── full description
├── environment
├── comments
├── work notes
└── resolution notes
expected knowledge decision
retrieval query variants
optional grounded article expectation
```

The benchmark loader validates that the labels agree with the Resolve domain policy:

| Closure evidence | Existing knowledge coverage | Expected action |
| --- | --- | --- |
| insufficient | not evaluated | `NO_ACTION` |
| sufficient | none | `CREATE` |
| sufficient | partial | `IMPROVE` |
| sufficient | sufficient | `REUSE` |

A `CREATE` case cannot declare reusable knowledge. A `NO_ACTION` case cannot execute retrieval. `CREATE` and `IMPROVE` cases must contain a Knowledge Article expectation grounded in supplied evidence.

## Evaluation projections

`tropos.evals.enterprise_support` loads the canonical case pack and projects it into the existing evaluation contracts.

### Retrieval

Each case can supply multiple query formulations for the same underlying incident:

- an error-code or identifier formulation;
- a natural-language symptom;
- a diagnostic or task-oriented formulation.

Negative cases add cross-tenant, restricted, ambiguous, and out-of-corpus queries.

The default projection returns **development** queries only. Holdout and challenge cases require an explicit split argument.

### Resolve decision

The same case pack projects to an `EvalDataset` containing expected closure evidence, knowledge coverage, action, and stable decision reason.

This creates a future executable target for case → retrieval → coverage → knowledge-action evaluation without inventing a second case corpus.

### Knowledge Article

`CREATE` and `IMPROVE` cases project to the existing Knowledge Article evaluation contract. Article expectations include:

- article type and subject;
- evidence excerpts;
- required sections;
- evidence-aligned claims;
- typed gaps when applicable;
- forbidden unsupported behavior.

The benchmark does not claim that the current Resolve runtime can yet generate every V1 article end to end. In particular, a genuinely new `CREATE` case requires the resolved-case evidence to become a first-class generation input; today's Knowledge Article application path primarily retrieves existing governed knowledge. The benchmark makes that product gap explicit rather than hiding it.

## Split design

V1 records development, holdout, and challenge cases.

The development split is the default API surface. Holdout/challenge require explicit selection, reducing accidental use during tuning.

This repository is public, so the holdout data is **not secret**. It is a locked-by-convention validation split, not a statistically pristine hidden test set. A future release benchmark that requires blind evaluation should store unseen labels outside the public tuning surface.

Each split contains all four Resolve outcomes so one split is not accidentally equivalent to one business action.

## Labeling and review protocol

V1 cases are human-authored synthetic specifications. `approved` means the case has passed the repository's structural and product-policy checks; it does **not** mean an independent domain expert has validated the scenario.

For each future case, the benchmark should preserve:

- the public failure pattern or observed defect that motivated the scenario;
- the resolved-case facts and resolution evidence;
- the intended Resolve action;
- retrieval relevance labels;
- article evidence and forbidden unsupported behavior where applicable;
- reviewer notes when a second human review becomes available.

Query wording should increasingly be authored independently from the target knowledge text. V1 does not yet satisfy QE-108's blinded query-authoring protocol, so lexical performance can be optimistic on some cases.

Dataset versions are immutable evidence snapshots. Material case, label, or expected-behavior changes require a new benchmark version rather than silently rewriting prior results.

## Statistical interpretation

The 48 retrieval queries are **not 48 independent real incidents**. Several are query formulations derived from the same underlying case. Treating those paraphrases as independent observations would understate uncertainty.

V1 therefore supports:

- functional regression discovery;
- strategy comparison by scenario;
- access-boundary checks;
- development of the unified evaluation runtime;
- validation of Resolve/Knowledge Article dataset contracts.

V1 does not support a claim of enterprise retrieval accuracy.

QE-108 still requires a larger benchmark with independent scenario units, chunk-level labels, locked holdout semantics, uncertainty reporting, and the planned minimum answerable/no-answer populations before release-quality use.

## Quality controls

The integration test verifies:

- balanced case actions;
- complete case-record fields;
- valid split projection;
- Resolve decision-policy consistency;
- valid article evidence references;
- no reusable label on `CREATE` cases;
- no retrieval execution on `NO_ACTION` cases;
- BM25 can execute every split;
- restricted knowledge does not cross the retrieval boundary for unauthorized queries.

## Next use

This benchmark should become the primary realistic dataset while the two retrieval-evaluation execution paths are unified.

After runtime convergence:

1. expand independent support scenarios toward QE-108 sample targets;
2. add chunk-level and graded relevance labels;
3. record scenario-level rather than paraphrase-level uncertainty;
4. calibrate abstention on development data;
5. evaluate the locked validation split;
6. wire resolved-case evidence into real Knowledge Article generation and execute real-model article evaluations.
