import time
import streamlit as st

from config.settings import Settings
from services.azure_openai_service import AzureOpenAIService
from services.chroma_service import ChromaService
from agents.step_definition_generator import StepDefinitionGeneratorAgent
from utils.helpers import sanitize_filename
from utils.logger import AppLogger

logger = AppLogger.get_logger("page.generate_step_definitions")

_LANG_EXT = {
    "Java Selenium Cucumber": ".java",
    "Python Behave": ".py",
    "C# SpecFlow": ".cs",
}
_LANG_SYNTAX = {
    "Java Selenium Cucumber": "java",
    "Python Behave": "python",
    "C# SpecFlow": "csharp",
}


def render_generate_step_definitions():
    st.markdown("## ⚙️ Generate Step Definitions")
    st.caption(
        "Upload a Gherkin .feature file and the AI will generate production-ready step "
        "definitions following Page Object Model. Previously generated steps are reused automatically."
    )

    # Show DOM context status banner when crawl data is available
    dom_text = st.session_state.get("crawl_dom_text", "")
    if dom_text:
        st.success(
            f"✓ DOM locator data available from web crawler "
            f"({len(st.session_state.get('crawl_pages_data', []))} pages). "
            "Step definitions will use **real element locators** instead of placeholders."
        )

    settings = Settings()
    if not settings.is_configured():
        st.error("⚠️ Azure OpenAI is not configured. Go to **Settings** first.")
        return

    # ------------------------------------------------------------------ #
    #  Inputs                                                              #
    # ------------------------------------------------------------------ #
    st.markdown("### 1. Upload Feature File")
    uploaded = st.file_uploader(
        "Select a .feature file",
        type=["feature", "txt"],
        help="Upload a Gherkin feature file",
    )

    st.markdown("### 2. Configure Output")
    c1, c2, c3 = st.columns(3)
    with c1:
        language = st.selectbox(
            "Language / Framework",
            options=list(_LANG_EXT.keys()),
            index=0,
        )
    with c2:
        page_name = st.text_input(
            "Page Object Class Name",
            placeholder="e.g. LoginPage, CheckoutPage",
        )
    with c3:
        namespace = st.text_input(
            "Package / Namespace",
            value="com.qa.stepdefinitions",
            placeholder="com.company.qa.steps",
        )

    # ------------------------------------------------------------------ #
    #  Generate                                                            #
    # ------------------------------------------------------------------ #
    st.markdown("### 3. Generate")
    if st.button(
        "🚀 Generate Step Definitions",
        type="primary",
        use_container_width=True,
        disabled=(uploaded is None),
    ):
        pname = page_name.strip() or "PageObject"
        _run_pipeline(
            uploaded_file=uploaded,
            settings=settings,
            language=language,
            page_name=pname,
            namespace=namespace,
        )

    if st.session_state.get("generated_step_definitions"):
        _render_results()


# ------------------------------------------------------------------ #
#  Pipeline                                                            #
# ------------------------------------------------------------------ #

def _run_pipeline(uploaded_file, settings, language, page_name, namespace):
    status_box = st.empty()
    progress = st.progress(0, "Initialising…")
    log_box = st.empty()
    logs: list[str] = []

    def log(msg: str, level: str = "INFO"):
        ts = time.strftime("%H:%M:%S")
        logs.append(f"[{level}] {ts}  {msg}")
        if level == "ERROR":
            logger.error(msg)
        else:
            logger.info(msg)
        log_box.code("\n".join(logs[-25:]), language=None)

    try:
        log(f"Feature file received: {uploaded_file.name}")
        feature_content = uploaded_file.read().decode("utf-8", errors="replace")
        log(f"Read {len(feature_content):,} characters")
        progress.progress(15, "Reading feature file…")

        log("Initialising Azure OpenAI and ChromaDB services")
        openai_svc = AzureOpenAIService(settings)
        chroma_svc = ChromaService(settings)
        progress.progress(30, "Searching step repository…")

        log(f"Agent 5: Step Definition Generator — target: {language}")
        log("Searching existing step repository for reusable methods")
        generator = StepDefinitionGeneratorAgent(openai_svc, chroma_svc)

        # Use real DOM locators if crawler data is available
        dom_context = st.session_state.get("crawl_dom_text", "")
        if dom_context:
            log(f"DOM locator context injected ({len(dom_context):,} chars) — steps will use real locators")
        else:
            log("No DOM data available — generating with generic locator placeholders")

        log(f"Sending request to Azure OpenAI (language={language}, page={page_name})")
        step_defs = generator.generate(feature_content, language, page_name, dom_context)
        log("Step definitions generated successfully")
        progress.progress(100, "Done!")

        ext = _LANG_EXT.get(language, ".java")
        filename = sanitize_filename(page_name) + "Steps" + ext

        st.session_state["generated_step_definitions"] = step_defs
        st.session_state["step_def_filename"] = filename
        st.session_state["step_def_language"] = language
        st.session_state["logs"] = logs

        status_box.success(
            f"✅ Step definitions generated | File: {filename} | "
            f"Azure tokens used: {openai_svc.total_tokens:,}"
        )

    except Exception as exc:
        log(f"Pipeline error: {exc}", "ERROR")
        logger.error("Step definition pipeline failed", exc_info=True)
        status_box.error(f"❌ Generation failed: {exc}")
        progress.empty()


# ------------------------------------------------------------------ #
#  Results                                                             #
# ------------------------------------------------------------------ #

def _render_results():
    st.markdown("---")
    st.markdown("### Generated Step Definitions")

    content = st.session_state["generated_step_definitions"]
    filename = st.session_state.get("step_def_filename", "StepDefinitions.java")
    language = st.session_state.get("step_def_language", "Java Selenium Cucumber")
    syntax = _LANG_SYNTAX.get(language, "java")

    dl_col, clear_col, info_col = st.columns([2, 2, 6])
    with dl_col:
        st.download_button(
            "⬇️ Download File",
            data=content.encode("utf-8"),
            file_name=filename,
            mime="text/plain",
            use_container_width=True,
        )
    with clear_col:
        if st.button("🗑️ Clear", use_container_width=True):
            for k in ("generated_step_definitions", "step_def_filename", "step_def_language"):
                st.session_state.pop(k, None)
            st.rerun()
    with info_col:
        st.caption(f"📁 {filename} | 📄 {len(content):,} characters | 🔧 {language}")

    st.code(content, language=syntax, line_numbers=True)
