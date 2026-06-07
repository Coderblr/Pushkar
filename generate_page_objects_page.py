"""
Page Object Generator page.

Combines:
  • DOM extraction data from the web crawler (or manually uploaded)
  • Generated step definitions
to produce complete, POM-compliant page classes with real locators.
"""

import time
import streamlit as st

from config.settings import Settings
from services.azure_openai_service import AzureOpenAIService
from services.dom_extractor import pages_to_pom_context
from agents.page_object_generator import PageObjectGeneratorAgent
from utils.helpers import sanitize_filename, clean_code_output
from utils.logger import AppLogger

logger = AppLogger.get_logger("page.generate_page_objects")

_LANG_SYNTAX = {
    "Java Selenium Cucumber": "java",
    "Python Behave": "python",
    "C# SpecFlow": "csharp",
}
_LANG_EXT = {
    "Java Selenium Cucumber": ".java",
    "Python Behave": ".py",
    "C# SpecFlow": ".cs",
}


def render_generate_page_objects_page():
    st.markdown("## 📦 Generate Page Objects")
    st.caption(
        "Generates Page Object Model classes using real DOM locators from the web crawler "
        "combined with your step definitions — no placeholder selectors."
    )

    settings = Settings()
    if not settings.is_configured():
        st.error("⚠️ Azure OpenAI not configured. Go to **Settings** first.")
        return

    # ------------------------------------------------------------------ #
    #  Source selection                                                    #
    # ------------------------------------------------------------------ #
    pages_data = st.session_state.get("crawl_pages_data")
    step_defs = st.session_state.get("generated_step_definitions", "")

    st.markdown("### Data Sources")
    src_col1, src_col2 = st.columns(2)

    with src_col1:
        st.markdown("**DOM Data (from Web Crawler)**")
        if pages_data:
            st.success(f"✓ {len(pages_data)} page(s) crawled and ready")
        else:
            st.warning("No crawl data in session — upload a DOM JSON or run the Web Crawler first.")
            dom_file = st.file_uploader(
                "Upload crawl JSON (exported from crawler)", type=["json"], key="dom_upload"
            )
            if dom_file:
                try:
                    import json
                    raw = json.loads(dom_file.read())
                    # Accept a simplified list of {page_name, url, elements:[{...}]}
                    st.session_state["crawl_dom_raw"] = raw
                    st.success(f"Loaded {len(raw)} page(s) from JSON")
                except Exception as e:
                    st.error(f"Invalid JSON: {e}")

    with src_col2:
        st.markdown("**Step Definitions**")
        if step_defs:
            st.success(f"✓ Step definitions in session ({len(step_defs):,} chars)")
        else:
            st.warning("No step definitions in session — upload a file.")
            step_file = st.file_uploader("Upload step definitions file", type=["java", "py", "cs", "txt"])
            if step_file:
                step_defs = step_file.read().decode("utf-8", errors="replace")
                st.session_state["generated_step_definitions"] = step_defs
                st.success("Step definitions loaded")

    # ------------------------------------------------------------------ #
    #  Options                                                             #
    # ------------------------------------------------------------------ #
    st.markdown("### Options")
    opt1, opt2 = st.columns(2)
    with opt1:
        language = st.selectbox(
            "Language / Framework",
            options=["Java Selenium Cucumber", "Python Behave", "C# SpecFlow"],
        )
    with opt2:
        pkg = st.text_input("Package / Namespace", value="com.qa.pages")

    selected_pages = None
    if pages_data:
        page_names = [p.page_name for p in pages_data]
        selected_names = st.multiselect(
            "Pages to generate (leave blank = all)",
            options=page_names,
            default=[],
        )
        if selected_names:
            selected_pages = [p for p in pages_data if p.page_name in selected_names]
        else:
            selected_pages = pages_data

    # ------------------------------------------------------------------ #
    #  Generate                                                            #
    # ------------------------------------------------------------------ #
    can_generate = bool((pages_data or st.session_state.get("crawl_dom_raw")) and step_defs)

    if st.button(
        "🚀 Generate Page Objects",
        type="primary",
        use_container_width=True,
        disabled=not can_generate,
    ):
        _run_pom_pipeline(
            settings=settings,
            pages=selected_pages or pages_data or [],
            step_defs=step_defs,
            language=language,
        )

    if not can_generate:
        st.info(
            "Need both DOM data and step definitions to generate page objects. "
            "Run the **Web Crawler** first, then **Generate Step Definitions**."
        )

    # ------------------------------------------------------------------ #
    #  Results                                                             #
    # ------------------------------------------------------------------ #
    if st.session_state.get("generated_page_objects"):
        _render_pom_results()


# ------------------------------------------------------------------ #
#  Pipeline                                                            #
# ------------------------------------------------------------------ #

def _run_pom_pipeline(settings, pages, step_defs, language):
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
        log(f"Generating page objects for {len(pages)} page(s) in {language}")
        progress.progress(10, "Initialising AI service…")

        openai_svc = AzureOpenAIService(settings)
        agent = PageObjectGeneratorAgent(openai_svc)

        results: dict[str, str] = {}
        for i, page in enumerate(pages):
            log(f"Processing: {page.page_name} ({i+1}/{len(pages)})")
            pct = 10 + int(80 * (i + 1) / len(pages))
            progress.progress(pct, f"Generating {page.page_name}…")

            page_results = agent.generate([page], step_defs, language)
            results.update(page_results)
            log(f"Generated: {list(page_results.keys())}")

        progress.progress(100, "Done!")
        st.session_state["generated_page_objects"] = results
        st.session_state["pom_language"] = language
        st.session_state["logs"] = logs

        status_box.success(
            f"✅ {len(results)} page object(s) generated | "
            f"Azure tokens: {openai_svc.total_tokens:,}"
        )

    except Exception as exc:
        log(f"Pipeline error: {exc}", "ERROR")
        logger.error("Page object pipeline failed", exc_info=True)
        status_box.error(f"❌ Failed: {exc}")
        progress.empty()


# ------------------------------------------------------------------ #
#  Results panel                                                       #
# ------------------------------------------------------------------ #

def _render_pom_results():
    pom = st.session_state["generated_page_objects"]
    language = st.session_state.get("pom_language", "Java Selenium Cucumber")
    syntax = _LANG_SYNTAX.get(language, "java")

    st.markdown("---")
    st.markdown(f"### Generated Page Objects ({len(pom)} file(s))")

    # ZIP download of all page objects
    from services.file_export_service import FileExportService
    zip_bytes = FileExportService.zip_files(pom)
    dl_col, clr_col, _ = st.columns([2, 2, 6])
    with dl_col:
        st.download_button(
            "⬇️ Download All (ZIP)",
            data=zip_bytes,
            file_name="page_objects.zip",
            mime="application/zip",
            use_container_width=True,
        )
    with clr_col:
        if st.button("🗑️ Clear", use_container_width=True, key="clr_pom"):
            st.session_state.pop("generated_page_objects", None)
            st.rerun()

    # Individual tabs
    if len(pom) == 1:
        fname, code = next(iter(pom.items()))
        st.caption(f"📁 {fname}")
        st.code(code, language=syntax, line_numbers=True)
    else:
        tabs = st.tabs(list(pom.keys()))
        for tab, (fname, code) in zip(tabs, pom.items()):
            with tab:
                st.download_button(
                    f"⬇️ {fname}",
                    data=code.encode(),
                    file_name=fname,
                    mime="text/plain",
                    key=f"dl_pom_{fname}",
                )
                st.code(code, language=syntax, line_numbers=True)
