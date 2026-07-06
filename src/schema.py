"""Structured output schema for the classifier.

Extends the legacy ``Prediction`` model with fields that separate genuine model
errors from data-capture gaps and make routing decisions auditable.
"""

from typing import Dict, List, Literal

from pydantic import BaseModel, Field

# The verdict the model may return. ``insufficient_evidence`` lets undetectable
# rows (e.g. content injected purely via CSS that is not present in the capture)
# surface as a data-capture flag instead of a silent wrong guess.
Classification = Literal["accessible", "inaccessible", "insufficient_evidence"]


class Prediction(BaseModel):
    classification: Classification = Field(
        description=(
            "'accessible' if the element and its context satisfy the applied "
            "WCAG success criteria; 'inaccessible' if at least one clear "
            "violation is found; 'insufficient_evidence' if the provided "
            "capture does not contain enough signal to decide (e.g. the "
            "relevant CSS or DOM node was not captured)."
        )
    )
    reason: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Mapping of WCAG success-criterion number (e.g. '1.1.1', '1.2.1', "
            "'1.3.1') to a concise technical justification citing the specific "
            "evidence field that proves the violation."
        ),
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Model confidence in the classification, from 0.0 to 1.0.",
    )
    evidence_citation: str = Field(
        default="",
        description=(
            "Short quote or reference to the specific evidence (e.g. an "
            "ax_subtree line or a screen-reader phrase) that drove the verdict."
        ),
    )

    # Populated by the pipeline (not the model) so the output CSV records which
    # skills were shown to the model for each row.
    applied_skills: List[str] = Field(
        default_factory=list,
        description="Technique ids of the skills the router selected for this element.",
    )
