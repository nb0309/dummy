import csv
import datetime
import os
import re
from dotenv import load_dotenv
load_dotenv()

from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field
import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

# ==========================================
# 1. SETUP & CONFIGURATION
# ==========================================

INPUT_CSV = "input.csv"
OUTPUT_CSV = "predictions_with_accessibility_analysis.csv"
LOG_FILE = "llm_calls.log"

# Load the dataset safely
if not os.path.exists(INPUT_CSV):
    raise FileNotFoundError(f"❌ Missing target scan file: {INPUT_CSV}. Ensure your pipeline has executed successfully first!")

dataset = pd.read_csv(INPUT_CSV)
print("Loaded dataset successfully:")
print(dataset.info())

class Prediction(BaseModel):
    classification: Literal["accessible", "inaccessible"] = Field(
        description="Either 'accessible' or 'inaccessible' based on whether the HTML and screen reader output meet WCAG Level A guidelines."
    )
    reason: Dict[str, str] = Field(
        default_factory=dict,
        description="Dictionary where the key is a WCAG rule (e.g., '1.1.1', '1.3.1') and the value is the reason for the violation."
    )

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    return value if value not in (None, "") else default

def load_llm() -> AzureChatOpenAI:
    azure_endpoint = _env("AZURE_OPENAI_ENDPOINT")
    azure_model = _env("AZURE_MODEL", "gpt-5")
    azure_api_version = _env("AZURE_API_VERSION", "2024-02-01")
    azure_api_key = _env("AZURE_API_KEY") or _env("openai")

    if not azure_endpoint:
        raise RuntimeError("Missing AZURE_OPENAI_ENDPOINT environment variable.")
    if not azure_api_version:
        raise RuntimeError("Missing AZURE_API_VERSION environment variable.")
    if not azure_api_key:
        raise RuntimeError("Missing AZURE_API_KEY environment variable.")

    return AzureChatOpenAI(
        azure_endpoint=azure_endpoint,
        model=azure_model,
        api_version=azure_api_version,
        api_key=azure_api_key,
    )

def clean_html(html: str) -> str:
    """Clean up mangled HTML for better LLM comprehension without breaking valid attributes."""
    if not isinstance(html, str) or html == "nan":
        return "No HTML context provided"
    
    html = re.sub(r'\s*data-scan-id="[^"]*"', '', html)
    html = re.sub(r'\s*data-parent-scan-id="[^"]*"', '', html)
    html = html.replace('=""', '=__EMPTY_QUOTE__')
    html = re.sub(r'="" ([^"<>]+?)""=""', r'="\1"', html)
    html = re.sub(r'""', r'"', html)
    html = html.replace('=__EMPTY_QUOTE__', '=""')
    html = re.sub(r'\n\s*\n\s*\n', '\n\n', html)
    return html.strip()

def log_llm_call(element_id: Any, messages: List[Any], response: Optional[Dict] = None, error: Optional[str] = None):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*80}\nSAMPLE ID: {element_id}\nSTATUS: {'SUCCESS' if not error else 'FAILED'}\n")
        if error: f.write(f"ERROR: {error}\n")
        else: f.write(f"RESPONSE: {response}\n")

# Initialize LLM infrastructure
llm = load_llm()
structured_llm = llm.with_structured_output(Prediction, method="function_calling")

with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write(f"LLM Call Log initialized on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

# ==========================================
# 2. PROCESSING THE DATAFRAME
# ==========================================

print("Starting processing of elements...")
processed_rows = []

# Tracker dictionary for mapping explicit WCAG Success Criteria frequencies
wcag_rule_metrics = {"1.1.1": 0, "1.2.1": 0, "1.3.1": 0}

for index, row in dataset.iterrows():
    # Updated to map directly to the new CSV column structure
    global_id = row.get("sample_id")
    element_type = row.get("element_type")
    raw_html = row.get("element_html_raw")
    parent_html = row.get("parent_html")
    screen_reader_output = row.get("sr_transcript")

    print(f"\nProcessing Sample ID: {global_id} ({element_type})")

    cleaned_html = clean_html(str(raw_html))
    cleaned_parent = clean_html(str(parent_html))

    review_content = {
        "element_type": str(element_type),
        "html_code": cleaned_html,
        "parent_context_html": cleaned_parent,
        "screen_reader_output": str(screen_reader_output)
    }

    messages = [
        SystemMessage(content="""You are a strict WCAG accessibility classifier evaluating components against WCAG 2.2 Level A criteria. 
You will be given an element's type, its source HTML code, its wrapping parent context markup, and its spoken text output from a screen reader simulation script.

Your reason keys must strictly be chosen from '1.1.1', '1.2.1', or '1.3.1'.

CRITICAL ENVIRONMENT LOGIC NOTE (THE JSDOM ENVIRONMENT BUG):
The testing script utilizes a headless JSDOM environment which lacks a genuine accessibility tree. Consequently, interactive checkboxes (`<input type="checkbox">`) and radio buttons (`<input type="radio">`) are routinely announced with the verbal prefix "textbox" instead of "checkbox" or "radio" (e.g., "textbox, Waste from animal..."). 
DO NOT flag an element as 'inaccessible' simply because a checkbox or radio button says "textbox". Instead, check if it has a valid structural relationship (associated label or containing fieldset).

CHECK THESE SPECIFIC SUCCESS CRITERIA:

1. 1.1.1 Non-text Content:
   - <img> tags without alt attributes, or screen reader output reading raw image filenames instead of descriptive content.
   - Using alt="" or role="presentation" on meaningful context images or brand logos where the file name or layout context implies vital textual orientation.

2. 1.1.1 & 1.2.1 Audio/Video Media:
   - <audio> or <video> blocks whose player control layers are skipped entirely or read as completely unlabelled actions.

3. 1.3.1 Info and Relationships (Core Component Layouts):
   - THE HIDDEN TEXT TRAP: When interactive actions (like an anchor <a> or a <button>) rely on visually hidden elements (e.g., `<span style="display:none"> about football</span>`) to provide vital distinct context, but that inner content is completely cut from the accessibility tree via `display:none` or `visibility:hidden`. If the screen reader output drops the contextual phrases and reads an ambiguous placeholder (like just "Read more"), flag this strictly as an 'inaccessible' 1.3.1 VIOLATION.
   - FORM CONTROL GROUPS: Related clusters of checkboxes or radio buttons addressing a unified prompt (e.g., a multi-select form) MUST be enclosed within a semantic `<fieldset>` wrapper containing a prompt-defining `<legend>`. Using loose heading tags (`<h4>`, `<p>`) right above a group of detached inputs is a structural 1.3.1 VIOLATION.
   - DATA TABLES RELATIONSHIPS: Data tables are navigated using explicit matrix cell prefixes (`[Cell R1C1]`, `[Row 2]`). Look at the matrix phrases. If a table contains data grid cells, but the screen reader output fails to speak corresponding column/row headers when navigating into rows, or if the table lacks proper structural headers (`<th>`) and instead relies completely on generic data slots (`<td>`) without layout structural roles, flag this as an 'inaccessible' 1.3.1 VIOLATION.
   - HEADING HIERARCHY: Visually styled layout text must map to semantic tags (`<h1>`-`<h6>`). Skipping levels downwards arbitrarily (e.g., `<h2>` straight down to `<h5>`) or structuring headings out of logical order is a 1.3.1 VIOLATION.

CLASSIFICATION OUTPUT RULES:
- "inaccessible": You encountered at least ONE clear WCAG violation defined above. Write the corresponding rule key ('1.1.1', '1.2.1', or '1.3.1') alongside a concise technical proof.
- CRITICAL: When evaluating individual form inputs or headings, look closely at the 'parent_context_html'. If the parent markup reveals that this specific element is part of a broken multi-input group (missing a fieldset) or a skipped heading sequence, you MUST flag this specific row as 'inaccessible' under key '1.3.1', even if the individual element looks fine on its own.
- "accessible": The element and its broader context follow structural, programmatic, and relational rules perfectly."""),
        HumanMessage(content=pd.Series(review_content).to_json())
    ]

    try:
        output = structured_llm.invoke(messages)
        prediction = output.classification.lower()
        violations_dict = output.reason
        log_llm_call(global_id, messages, response=output.model_dump())
        
        # If the element is inaccessible, extract and tally the targeted rule keys
        if prediction == "inaccessible" and isinstance(violations_dict, dict):
            for rule in violations_dict.keys():
                cleaned_rule = rule.strip()
                if cleaned_rule in wcag_rule_metrics:
                    wcag_rule_metrics[cleaned_rule] += 1
                else:
                    wcag_rule_metrics[cleaned_rule] = 1

    except Exception as e:
        print(f"Error processing row {index}: {e}")
        prediction = "error"
        violations_dict = {"error": str(e)}
        log_llm_call(global_id, messages, error=str(e))

    print(f" -> Predicted: {prediction}")
    if violations_dict:
        print(f" -> Reason: {violations_dict}")

    row_dict = row.to_dict()
    row_dict["Prediction"] = prediction
    row_dict["Reason"] = violations_dict if violations_dict else None
    processed_rows.append(row_dict)

output_df = pd.DataFrame(processed_rows)
output_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")

print(f"\nProcessing complete! Main Results saved to: {OUTPUT_CSV}")

# ==========================================
# 3. METRICS EVALUATION & SUMMARY PRINTING
# ==========================================
print("\n" + "=" * 50)
print("       COMPREHENSIVE RUN METRICS RUN SUMMARY")
print("=" * 50)

prediction_counts = output_df["Prediction"].value_counts()
total_elements = len(output_df)

accessible_count = prediction_counts.get("accessible", 0)
inaccessible_count = prediction_counts.get("inaccessible", 0)
error_count = prediction_counts.get("error", 0)

print(f"Total Evaluated DOM Elements : {total_elements}")
print(f"🟢 Predicted ACCESSIBLE     : {accessible_count} ({accessible_count / total_elements * 100:.1f}%)")
print(f"🔴 Predicted INACCESSIBLE   : {inaccessible_count} ({inaccessible_count / total_elements * 100:.1f}%)")

if error_count > 0:
    print(f"⚠️ Processing Runtime Errors: {error_count} ({error_count / total_elements * 100:.1f}%)")

print("-" * 50)
print("     SPECIFIC WCAG VIOLATION CLASS BREAKDOWN")
print("-" * 50)
for criteria, count in wcag_rule_metrics.items():
    print(f"Rule Code {criteria.ljust(6)} : {count} occurrences found")

print("-" * 50)
print("File-Level Verification Metrics Summary:")

# Updated file verdicts: Group by 'source_file' instead of 'File Name'
file_summary = output_df.groupby("source_file")["Prediction"].apply(
    lambda x: "inaccessible" if "inaccessible" in x.values else "accessible"
).reset_index()

total_files = len(file_summary)
failed_files_count = len(file_summary[file_summary["Prediction"] == "inaccessible"])

print(f"Total Unique HTML Test Files Audited : {total_files}")
print(f"❌ Files Flagged with WCAG Violations: {failed_files_count} ({failed_files_count / total_files * 100:.1f}%)")
print(f"🎯 True File-Level Audit Accuracy    : {failed_files_count / total_files * 100:.1f}% (Target: 100.0%)")
print("=" * 50)