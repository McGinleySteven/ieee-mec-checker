import streamlit as st
from pypdf import PdfReader
import re
import base64
from collections import defaultdict

st.set_page_config(page_title="IEEE MEC Pre-Check", layout="wide")

MODAL_VERBS = {
    "shall": r"\bshall\b", "shall not": r"\bshall not\b",
    "should": r"\bshould\b", "should not": r"\bshould not\b",
    "may": r"\bmay\b", "need not": r"\bneed not\b",
    "can": r"\bcan\b", "cannot": r"\bcannot\b",
}

DISCOURAGED_TERMS = {
    "must": {"regex": r"\bmust\b", "reason": "Use 'shall' for mandatory obligations."},
    "will": {"regex": r"\bwill\b", "reason": "Only permitted for factual statements."},
    "etc.": {"regex": r"\betc\b\.?", "reason": "Ambiguous; specify exact requirements."},
    "and/or": {"regex": r"\band/or\b", "reason": "Rephrase as 'A or B, or both'."},
    "e.g.": {"regex": r"\be\.g\.\b", "reason": "Replace with 'for example'."},
    "i.e.": {"regex": r"\bi\.e\.\b", "reason": "Replace with 'that is'."},
}

VAGUE_QUALIFIERS = [r"\badequate\b", r"\bas necessary\b", r"\bsufficient\b", r"\btimely\b"]
TRADEMARK_SYMBOLS = [r"™", r"®"]
MANDATORY_CLAUSES = {
    "Clause 1 (Overview)": r"(?:clause\s+1\b|^1\b[\.\s]+overview|^1\b[\.\s]+scope)",
    "Clause 2 (Normative refs)": r"(?:clause\s+2\b|^2\b[\.\s]+normative references)",
    "Clause 3 (Definitions)": r"(?:clause\s+3\b|^3\b[\.\s]+definitions)",
    "Clause 2 Boilerplate": r"indispensable for the application of this document",
}

class DraftAuditor:
    def __init__(self, file_obj):
        self.reader = PdfReader(file_obj)
        self.total_pages = len(self.reader.pages)
        self.pages_text = {idx + 1: (page.extract_text() or "") for idx, page in enumerate(self.reader.pages)}
        self.modal_counts = defaultdict(int)
        self.modal_occurrences = defaultdict(list)
        self.issues = []
        self.clause_matches = {k: [] for k in MANDATORY_CLAUSES}
        self.has_continuous_lines = False
        self.copyright_found = False

    def run_audit(self):
        self._check_modal_verbs()
        self._check_discouraged_and_vague()
        self._check_commercial_symbols()
        self._check_mandatory_clauses()
        self._check_mechanics()

    def _check_modal_verbs(self):
        for page_num, text in self.pages_text.items():
            for label, pattern in MODAL_VERBS.items():
                matches = re.findall(pattern, text, flags=re.IGNORECASE)
                if matches:
                    self.modal_counts[label] += len(matches)
                    self.modal_occurrences[label].append(page_num)

    def _check_discouraged_and_vague(self):
        for page_num, text in self.pages_text.items():
            for line in text.splitlines():
                line_str = line.strip()
                if not line_str: continue
                for term, meta in DISCOURAGED_TERMS.items():
                    if re.search(meta["regex"], line_str, flags=re.IGNORECASE):
                        self.issues.append({"severity": "Warning", "page": page_num, "term": term, "snippet": line_str[:80], "rec": meta["reason"]})
                for pattern in VAGUE_QUALIFIERS:
                    match = re.search(pattern, line_str, flags=re.IGNORECASE)
                    if match:
                        self.issues.append({"severity": "Editorial Note", "page": page_num, "term": match.group(0), "snippet": line_str[:80], "rec": "Specify exact testable metrics."})

    def _check_commercial_symbols(self):
        for page_num, text in self.pages_text.items():
            for sym in TRADEMARK_SYMBOLS:
                if sym in text:
                    self.issues.append({"severity": "Legal", "page": page_num, "term": sym, "snippet": f"Symbol '{sym}' found", "rec": "Avoid trademark symbols in normative text."})

    def _check_mandatory_clauses(self):
        for page_num, text in self.pages_text.items():
            for clause, pattern in MANDATORY_CLAUSES.items():
                if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
                    self.clause_matches[clause].append(page_num)

    def _check_mechanics(self):
        numbered_pages = 0
        for text in self.pages_text.values():
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if sum(1 for l in lines if re.match(r"^\d{1,3}\b", l)) >= 10:
                numbered_pages += 1
            if re.search(r"Copyright\s+(?:©|\(c\))\s+\d{4}\s+IEEE", text, flags=re.IGNORECASE):
                self.copyright_found = True
        if numbered_pages >= max(3, int(self.total_pages * 0.3)):
            self.has_continuous_lines = True

st.title("📄 IEEE SA Draft MEC Audit Pre-Check")
st.markdown("Upload a draft standard PDF to check for mandatory clauses, standards verbs, and editorial flags.")

uploaded_file = st.file_uploader("Upload IEEE Draft PDF", type="pdf")

if uploaded_file is not None:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Document Viewer")
        base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf"></iframe>'
        st.markdown(pdf_display, unsafe_allow_html=True)

    with col2:
        st.subheader("MEC Audit Report")
        with st.spinner("Analyzing PDF..."):
            auditor = DraftAuditor(uploaded_file)
            auditor.run_audit()

        st.write(f"**Total Pages Analyzed:** {auditor.total_pages}")
        
        st.markdown("### 1. Mandatory Clause Integrity")
        for clause, pages in auditor.clause_matches.items():
            if pages:
                st.success(f"✅ **{clause}**: Found (Pages: {pages[:3]})")
            else:
                st.error(f"❌ **{clause}**: MISSING")

        st.markdown("### 2. Document Mechanics")
        if auditor.has_continuous_lines:
            st.success("✅ Line Numbers Detected")
        else:
            st.error("❌ Missing Line Numbers (MEC FAIL)")
            
        if auditor.copyright_found:
            st.success("✅ IEEE Copyright Notice Found")
        else:
            st.error("❌ IEEE Copyright Notice Missing")

        st.markdown("### 3. Standards Verbs (Modal Usage)")
        verb_data = [{"Verb": k, "Count": auditor.modal_counts[k], "Pages": str(list(set(auditor.modal_occurrences[k]))[:5])} for k in MODAL_VERBS]
        st.dataframe(verb_data, use_container_width=True)

        st.markdown("### 4. Editorial Flags")
        if not auditor.issues:
            st.success("No prohibited terms or ambiguous qualifiers flagged.")
        else:
            st.warning(f"Found {len(auditor.issues)} potential editorial issues.")
            for issue in auditor.issues:
                with st.expander(f"[{issue['severity']}] {issue['term']} (Page {issue['page']})"):
                    st.write(f"**Context:** \"{issue['snippet']}...\"")
                    st.write(f"**Guidance:** {issue['rec']}")
