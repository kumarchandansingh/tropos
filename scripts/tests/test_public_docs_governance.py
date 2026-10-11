from __future__ import annotations

import unittest

from scripts import check_public_docs as docs_gate


class DocumentationGovernanceTests(unittest.TestCase):
    def test_documentation_na_requires_checked_box_and_substantive_rationale(self) -> None:
        valid = """
## Documentation impact
- [x] Documentation impact is N/A

## Documentation rationale
This refactor preserves the public capability, architecture, evaluation semantics, and delivery controls.
"""
        too_short = """
## Documentation impact
- [x] Documentation impact is N/A

## Documentation rationale
No public change.
"""
        unchecked = valid.replace("- [x]", "- [ ]")

        self.assertTrue(docs_gate._documentation_na_has_rationale(valid))
        self.assertFalse(docs_gate._documentation_na_has_rationale(too_short))
        self.assertFalse(docs_gate._documentation_na_has_rationale(unchecked))

    def test_change_classification_separates_product_eval_and_delivery_controls(self) -> None:
        self.assertTrue(
            docs_gate._is_material_product_change(
                "apps/api/src/tropos/core/adapters/retrieval/exact_vector.py"
            )
        )
        self.assertTrue(
            docs_gate._is_eval_change("apps/api/src/tropos/evals/experiments.py")
        )
        self.assertTrue(docs_gate._is_delivery_change(".github/workflows/ci.yml"))

        self.assertFalse(
            docs_gate._is_material_product_change(
                "apps/api/tests/unit/evals/test_experiments.py"
            )
        )

    def test_learning_note_does_not_satisfy_authoritative_documentation_impact(self) -> None:
        self.assertFalse(docs_gate._is_authoritative_doc("docs/learning/DENSE_RETRIEVAL_V1.md"))
        self.assertTrue(docs_gate._is_authoritative_doc("docs/architecture/RAG_ARCHITECTURE.md"))
        self.assertTrue(docs_gate._is_authoritative_doc("docs/quality/EVAL_STRATEGY.md"))

    def test_private_meta_patterns_target_author_facing_material_not_technical_resume_verb(
        self,
    ) -> None:
        text = "The sync worker can resume from a durable checkpoint."
        self.assertFalse(any(pattern.search(text) for pattern in docs_gate.PRIVATE_META_PATTERNS))

        private_text = "Use this as an interview-ready sample answer."
        self.assertTrue(
            any(pattern.search(private_text) for pattern in docs_gate.PRIVATE_META_PATTERNS)
        )


if __name__ == "__main__":
    unittest.main()
