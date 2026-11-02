import streamlit as st
from pypdf import PdfReader
import re
import base64
from collections import defaultdict

st.set_page_config(page_title="IEEE SA Draft MEC Pre-Check", layout="wide")

# --- Rules and Dictionaries ---
MODAL_VERBS = {
    "shall": r"\bshall\b", "shall not": r"\bshall not\b",
    "should": r"\bshould\b", "should not": r"\bshould not\b",
    "may": r"\bmay\b", "need not": r"\bneed not\b",
    "can": r"\bcan\b", "cannot": r"\bcannot\b",
}

DISCOURAGED_TERMS = {
    "must": {"regex": r"\bmust\b", "reason": "Use 'shall' for mandatory obligations."},
    "will": {"regex": r"\bwill\b", "reason": "Permitted only for factual statements or IEEE intent."},
    "etc.": {"regex": r"\betc\b\.?", "reason": "Ambiguous phrasing; specify exact requirements."},
    "and/or": {"regex": r"\band/or\b", "reason": "Rephrase as 'A or B, or both'."},
    "e.g.": {"regex": r"\be\.g\.\b", "reason": "Replace with 'for example' in normative text."},
    "i.e.": {"regex": r"\bi\.e\.\b", "reason": "Replace with 'that is' in normative text."},
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
        self.numbered_pages_list = []
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
                        self.issues.append({"severity": "Warning", "page": page_num, "term": term, "snippet": line_str[:85], "rec": meta["reason"]})
                for pattern in VAGUE_QUALIFIERS:
                    match = re.search(pattern, line_str, flags=re.IGNORECASE)
                    if match:
                        self.issues.append({"severity": "Editorial Note", "page": page_num, "term": match.group(0), "snippet": line_str[:85], "rec": "Specify exact testable metrics."})

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
        for page_num, text in self.pages_text.items():
            is_page_numbered = False
            
            # Strategy A: Check for consecutive numbers (e.g. 1, 2, 3, 4, 5...)
            tokens = re.findall(r'\b([1-9]|[1-4][0-9])\b', text)
            int_tokens = [int(t) for t in tokens]
            max_consecutive = 0
            curr = 1
            for i in range(1, len(int_tokens)):
                if int_tokens[i] == int_tokens[i-1] + 1:
                    curr += 1
                    if curr > max_consecutive:
                        max_consecutive = curr
                elif int_tokens[i] == int_tokens[i-1]:
                    continue
                else:
                    curr = 1
            if max_consecutive >= 4:
                is_page_numbered = True

            # Strategy B: Check lines starting with digits (1-50)
            if not is_page_numbered:
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                line_starts = sum(1 for l in lines if re.match(r'^(?:[1-9]|[1-4][0-9])\b', l))
                if line_starts >= 4:
                    is_page_numbered = True

            # Strategy C: Check space-separated margin sequences
            if not is_page_numbered and re.search(r'\b1\s+2\s+3\s+4\b', text):
                is_page_numbered = True

            if is_page_numbered:
                self.numbered_pages_list.append(page_num)

            # Check Copyright Notice
            if re.search(r"Copyright\s+(?:©|\(c\))\s+\d{4}\s+IEEE", text, flags=re.IGNORECASE):
                self.copyright_found = True

        # If at least 3 body pages have verified sequential line numbers, standard passes
        if len(self.numbered_pages_list) >= 3:
            self.has_continuous_lines = True


# --- GUI Application ---
st.title("📄 IEEE SA Draft MEC Audit Pre-Check")
st.markdown("Upload a draft standard PDF to check for line numbers, mandatory clauses, standards verbs, and editorial flags.")

uploaded_file = st.file_uploader("Upload IEEE Draft PDF", type="pdf")

if uploaded_file is not None:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Document Viewer")
        file_bytes = uploaded_file.getvalue()
        base64_pdf = base64.b64encode(file_bytes).decode('utf-8')
        
        # Object tag with embedded fallback for Chromium / Edge sandboxing
        pdf_display = f'''
            <object data="data:application/pdf;base64,{base64_pdf}" type="application/pdf" width="100%" height="800px">
                <div style="padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                    <p>Your browser blocked the inline preview of this 2.5MB file.</p>
                    <a href="data:application/pdf;base64,{base64_pdf}" download="{uploaded_file.name}">
                        Click here to download / open PDF locally
                    </a>
                </div>
            </object>
        '''
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
            sample_pgs = str(auditor.numbered_pages_list[:8]) + ("..." if len(auditor.numbered_pages_list) > 8 else "")
            st.success(f"✅ Line Numbers Detected across {len(auditor.numbered_pages_list)} pages (e.g. Pages {sample_pgs})")
        else:
            st.error("❌ Missing Line Numbers (MEC FAIL)")
            
        if auditor.copyright_found:
            st.success("✅ IEEE Copyright Notice Found")
        else:
            st.error("❌ IEEE Copyright Notice Missing")

        st.markdown("### 3. Standards Verbs (Modal Usage)")
        verb_data = [{"Verb": k, "Count": auditor.modal_counts[k], "Pages": str(list(set(auditor.modal_occurrences[k]))[:6])} for k in MODAL_VERBS]
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
