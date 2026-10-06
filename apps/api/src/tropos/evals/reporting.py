"""Business-readable exports derived only from saved observations."""

from statistics import fmean

from tropos.evals.catalogue import Json, array, object_value


def aggregate(cases: list[Json]) -> dict[str, Json]:
    completed = [
        object_value(c["metrics"])
        for raw in cases
        if (c := object_value(raw))["state"] in {"passed", "failed"}
    ]
    metrics = [m for m in completed if m.get("valid_for_quality_metrics") is True]
    result: dict[str, Json] = {
        "executed_without_error": len(completed),
        "valid_quality_cases": len(metrics),
        "excluded_from_metrics": len(cases) - len(metrics),
        "label_scope": "knowledge_id",
        "precision_denominator": 5,
    }
    for name in (
        "recall_at_1",
        "recall_at_3",
        "recall_at_5",
        "precision_at_5",
        "reciprocal_rank",
        "no_answer_correct",
    ):
        values = [float(value) for m in metrics if isinstance(value := m.get(name), int | float)]
        result[name] = fmean(values) if values else None
        result[name + "_case_count"] = len(values)
    return result


def safe(value: Json) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "\\|")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def markdown(report: dict[str, Json]) -> str:
    if "definition" in report:
        definition = object_value(report["definition"])
        lines = [
            "# Tropos planned retrieval tests",
            "",
            "Synthetic development catalogue. Listing these cases does not execute them.",
            "",
            "| Scenario | Purpose | Approval | Execution | Expected evidence |",
            "| --- | --- | --- | --- | --- |",
        ]
        for raw in array(definition["cases"]):
            case = object_value(raw)
            expected = ", ".join(safe(k) for k in array(case["relevant_knowledge_ids"]))
            lines.append(
                f"| {safe(case['case_id'])} | {safe(case['purpose'])} | "
                f"{safe(case['status'])} | Not run by this command | "
                f"{expected or 'No evidence'} |"
            )
        return "\n".join(lines) + "\n"
    lines = [
        "# Tropos retrieval evaluation",
        "",
        f"**Run outcome: {safe(report['outcome'])}.** Execution status: {safe(report['status'])}.",
        "",
        "Synthetic development evidence; this is not a production accuracy claim.",
        "",
        f"Dataset: {safe(report['dataset_id'])} / {safe(report['dataset_version'])}",
        "",
        f"Run: {safe(report['run_id'])}",
        "",
        "| Scenario | Expected evidence | Actual evidence in rank order | Outcome |",
        "| --- | --- | --- | --- |",
    ]
    for raw in array(report["cases"]):
        case = object_value(raw)
        definition = object_value(case["definition"])
        expected = ", ".join(safe(k) for k in array(definition["relevant_knowledge_ids"]))
        actual = []
        for hit_raw in array(case["actual"]):
            hit = object_value(hit_raw)
            actual.append(
                "Withheld: invariant violation"
                if hit["redacted"]
                else f"{safe(hit['rank'])}. {safe(hit['title'])}"
            )
        state = safe(case["state"])
        observation = "; ".join(actual) or (
            "No evidence returned" if state in {"passed", "failed"} else "No completed observation"
        )
        lines.append(
            f"| {safe(definition['case_id'])} | {expected or 'No evidence'} | "
            f"{observation} | {state} |"
        )
    lines.extend(["", "## Case evidence", ""])
    for raw in array(report["cases"]):
        case = object_value(raw)
        definition = object_value(case["definition"])
        lines.extend(
            [
                f"### {safe(definition['case_id'])}",
                "",
                f"Purpose: {safe(definition['purpose'])}",
                "",
                f"Question: {safe(definition['query'])}",
                "",
            ]
        )
        if case["error"]:
            lines.extend([f"Execution error: {safe(case['error'])}.", ""])
        for raw_check in array(case["assertions"]):
            check = object_value(raw_check)
            lines.append(f"- {'Pass' if check['passed'] else 'Fail'}: {safe(check['detail'])}.")
        for hit_raw in array(case["actual"]):
            hit = object_value(hit_raw)
            if not hit["redacted"]:
                lines.extend(
                    [
                        "",
                        f"Evidence: {safe(hit['text'])}",
                        "",
                        f"Source version: {safe(hit['source_version'])}; "
                        f"chunk: {safe(hit['chunk_id'])}.",
                    ]
                )
        lines.append("")
    provenance = object_value(report["provenance"])
    lines.extend(
        [
            "## Reproduction trace",
            "",
            f"Code revision: {safe(provenance['code_revision'])}",
            "",
            f"Working tree modified: {safe(provenance.get('working_tree_dirty'))}",
            "",
            f"Dataset digest: {safe(report['dataset_digest'])}",
            "",
            f"Dependency digest: {safe(provenance['dependency_digest'])}",
            "",
            "This saved report makes no model calls. Metrics in the JSON export retain "
            "denominators and distinguish unexecuted cases from completed failures.",
        ]
    )
    return "\n".join(lines) + "\n"
