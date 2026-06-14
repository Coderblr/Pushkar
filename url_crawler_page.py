"""
Web Application Crawler — powered by SmartCrawler.

SmartCrawler runs automatically:
  Phase 1 → URL-based crawl   (hyperlinks, public pages, direct URLs)
  Phase 2 → Sidebar navigation (clicks every menu → submenu → form)
  Phase 3 → Deduplication     (merges both, keeps unique views only)

The user just provides URL + credentials and gets a complete DOM map
of the entire application.
"""

import time
import streamlit as st
import pandas as pd
from pathlib import Path
from collections import Counter

from config.settings import Settings
from services.smart_crawler import SmartCrawler
from services.web_crawler import summarize_crawl_for_llm
from services.dom_extractor import elements_to_step_context
from agents.url_analyzer_agent import URLAnalyzerAgent
from agents.qa_review_agent import QAReviewAgent
from agents.duplicate_detection_agent import DuplicateDetectionAgent
from utils.helpers import count_scenarios, sanitize_filename
from utils.logger import AppLogger

logger = AppLogger.get_logger("page.url_crawler")


def render_url_crawler_page():
    st.markdown("## 🌐 Generate from Web Application")
    st.caption(
        "Enter the URL and credentials of your web application. "
        "The **Smart Crawler** automatically combines URL crawling AND sidebar navigation — "
        "it follows every hyperlink AND clicks through every sidebar menu / submenu / form. "
        "Nothing is missed."
    )

    settings = Settings()
    if not settings.is_configured():
        st.error("⚠️ Azure OpenAI not configured. Go to **Settings** first.")
        return

    try:
        import playwright  # noqa: F401
    except ImportError:
        st.error(
            "Playwright not installed.\n\n"
            "```\npip install playwright\nplaywright install chromium\n```"
        )
        return

    # ------------------------------------------------------------------ #
    #  How it works                                                        #
    # ------------------------------------------------------------------ #
    with st.expander("ℹ️ How Smart Crawl works", expanded=False):
        st.markdown(
            """
| Phase | What it does | Catches |
|-------|-------------|---------|
| **1 · URL Crawl** | Follows every `<a href>` link within the same domain | Public pages, login page, registration, direct-URL routes |
| **2 · Sidebar Crawl** | Clicks every menu item → expands sub-menus → clicks every leaf item | Dashboard forms, RTGS, NEFT, Teller Ops, Customer Ops — anything behind the sidebar |
| **3 · Deduplication** | Merges both results, removes pages with identical content fingerprints | Clean, unique page list with no repetition |

For every view/form found, it extracts:
- Every **input field** (text, email, password, date, dropdown, checkbox, radio, file …)
- Every **button** (submit, action, icon)
- Every **table** (headers + row count)
- **Locators** in priority order: `data-testid` → `id` → `name` → `aria-label` → CSS → XPath
            """
        )

    # ------------------------------------------------------------------ #
    #  Input form                                                          #
    # ------------------------------------------------------------------ #
    with st.form("crawl_form", clear_on_submit=False):
        st.markdown("### 1. Application URL")
        col_url, col_login = st.columns([3, 2])
        with col_url:
            base_url = st.text_input(
                "Web Application URL",
                placeholder="https://your-app.example.com",
            )
        with col_login:
            login_url = st.text_input(
                "Login Page URL",
                placeholder="Leave blank to use the App URL",
            )

        st.markdown("### 2. Credentials")
        a1, a2 = st.columns(2)
        with a1:
            username = st.text_input("Username / Email / User ID",
                                     placeholder="admin@company.com")
        with a2:
            password = st.text_input("Password", type="password")

        st.markdown("### 3. Selector Hints *(leave blank — auto-detected)*")
        s1, s2, s3 = st.columns(3)
        with s1:
            username_sel = st.text_input("Username field CSS",
                                         placeholder="input[name='email']")
        with s2:
            password_sel = st.text_input("Password field CSS",
                                         placeholder="input[type='password']")
        with s3:
            submit_sel = st.text_input("Submit button CSS",
                                       placeholder="button[type='submit']")

        st.markdown("### 4. Settings")
        cfg1, cfg2, cfg3, cfg4, cfg5 = st.columns(5)
        with cfg1:
            max_url_pages = st.number_input("Max URL pages", 1, 20, 8,
                                            help="Phase 1 — max hyperlink pages to follow")
        with cfg2:
            max_sidebar   = st.number_input("Max sidebar views", 5, 100, 40,
                                            help="Phase 2 — max sidebar menu items to visit")
        with cfg3:
            headless      = st.checkbox("Headless", value=True,
                                        help="Uncheck to watch the browser")
        with cfg4:
            module_name   = st.text_input("Feature Name",
                                          placeholder="SBI TGEN, Banking Portal…")
        with cfg5:
            run_qa_review = st.checkbox("QA Review", value=True)

        submitted = st.form_submit_button(
            "🚀 Smart Crawl & Generate",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if not base_url.strip():
            st.error("Please enter the application URL.")
            return
        _run_pipeline(
            base_url=base_url.strip(),
            username=username.strip(),
            password=password,
            login_url=(login_url.strip() or base_url.strip()),
            max_url_pages=int(max_url_pages),
            max_sidebar_views=int(max_sidebar),
            headless=headless,
            module_name=module_name.strip() or _default_module(base_url),
            username_sel=username_sel.strip(),
            password_sel=password_sel.strip(),
            submit_sel=submit_sel.strip(),
            run_qa_review=run_qa_review,
            settings=settings,
        )

    if st.session_state.get("crawl_pages_data"):
        _render_crawl_results()

    if st.session_state.get("generated_feature_file"):
        _render_feature_result()


# ------------------------------------------------------------------ #
#  Pipeline                                                            #
# ------------------------------------------------------------------ #

def _run_pipeline(
    base_url, username, password, login_url,
    max_url_pages, max_sidebar_views,
    headless, module_name,
    username_sel, password_sel, submit_sel,
    run_qa_review, settings,
):
    for k in ("crawl_pages_data", "crawl_dom_text", "crawl_summary",
              "crawl_base_url", "generated_feature_file",
              "generated_step_definitions", "generated_page_objects"):
        st.session_state.pop(k, None)

    status_box = st.empty()
    progress   = st.progress(0, "Initialising Smart Crawler…")
    log_box    = st.empty()
    logs: list[str] = []

    def log(msg: str, level: str = "INFO"):
        ts = time.strftime("%H:%M:%S")
        logs.append(f"[{level}] {ts}  {msg}")
        if level == "ERROR":
            logger.error(msg)
        else:
            logger.info(msg)
        log_box.code("\n".join(logs[-45:]), language=None)

    try:
        log(f"Target : {base_url}")
        log(f"Auth   : {'yes — ' + username if username else 'none (public)'}")
        log(f"Phases : URL crawl (max {max_url_pages}) + Sidebar crawl (max {max_sidebar_views})")
        progress.progress(5, "Phase 1 — URL crawl…")

        crawler = SmartCrawler(
            base_url=base_url,
            username=username,
            password=password,
            login_url=login_url,
            username_selector=username_sel,
            password_selector=password_sel,
            submit_selector=submit_sel,
            max_url_pages=max_url_pages,
            max_sidebar_views=max_sidebar_views,
            headless=headless,
            progress_callback=log,
            screenshot_dir="./logs/screenshots",
        )

        pages = crawler.crawl()
        progress.progress(55, f"{len(pages)} unique views — generating feature file…")

        total_el = sum(len(p.elements) for p in pages)
        log(f"Combined result: {len(pages)} unique views, {total_el} elements")

        st.session_state["crawl_pages_data"] = pages
        st.session_state["crawl_base_url"]   = base_url
        st.session_state["crawl_dom_text"]   = elements_to_step_context(pages)
        st.session_state["crawl_summary"]    = summarize_crawl_for_llm(pages)

        log("Sending crawl data to Azure OpenAI for feature file generation")
        openai_svc = AzureOpenAIService(settings)
        chroma_svc = ChromaService(settings)
        progress.progress(62, "Generating feature file…")

        feature_file = URLAnalyzerAgent(openai_svc, chroma_svc).generate(
            st.session_state["crawl_summary"], module_name
        )
        log("Feature file draft ready")
        progress.progress(78, "QA review…" if run_qa_review else "Finalising…")

        if run_qa_review:
            log("QAReviewAgent: quality review")
            feature_file = QAReviewAgent(openai_svc).review(feature_file)
            log("QA review complete")
        progress.progress(90, "Duplicate check…")

        dup = DuplicateDetectionAgent(chroma_svc).check_and_store(feature_file)
        log(f"Unique scenarios: {dup['unique']} | Duplicates removed: {dup['duplicates']}")
        progress.progress(100, "Done!")

        st.session_state["generated_feature_file"] = feature_file
        st.session_state["feature_file_name"]      = sanitize_filename(module_name) + ".feature"
        st.session_state["logs"]                   = logs

        status_box.success(
            f"✅ {len(pages)} views · {total_el} elements · "
            f"{count_scenarios(feature_file)} Gherkin scenarios · "
            f"Azure tokens: {openai_svc.total_tokens:,}"
        )

    except Exception as exc:
        log(f"Pipeline error: {exc}", "ERROR")
        logger.error("Smart crawl pipeline failed", exc_info=True)
        status_box.error(f"❌ Failed: {exc}")
        progress.empty()


# keep these imports at function scope to avoid circular imports at module load
def _ai_imports():
    from services.azure_openai_service import AzureOpenAIService
    from services.chroma_service import ChromaService
    return AzureOpenAIService, ChromaService

# patch into local namespace for the pipeline function above
from services.azure_openai_service import AzureOpenAIService  # noqa: E402
from services.chroma_service import ChromaService              # noqa: E402


# ------------------------------------------------------------------ #
#  Results panels                                                      #
# ------------------------------------------------------------------ #

def _render_crawl_results():
    pages = st.session_state.get("crawl_pages_data", [])
    if not pages:
        return

    total_el    = sum(len(p.elements) for p in pages)
    total_forms = sum(len(p.forms)    for p in pages)
    total_tbl   = sum(len(p.tables)   for p in pages)

    st.markdown("---")
    st.markdown(f"### 🗺️ Extraction Results — {len(pages)} Unique Views")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Unique Views",  len(pages))
    m2.metric("DOM Elements",  total_el)
    m3.metric("Forms",         total_forms)
    m4.metric("Tables",        total_tbl)

    # Per-view breakdown in tabs
    st.markdown("#### View-by-View DOM Breakdown")
    tab_labels = [p.page_name[:22] for p in pages]
    tabs = st.tabs(tab_labels)

    for tab, page in zip(tabs, pages):
        with tab:
            left, right = st.columns([1, 3])

            with left:
                st.markdown(f"**View:** {page.page_name}")
                if page.h1:
                    st.markdown(f"**H1:** {page.h1}")
                st.markdown(f"**URL:** `{page.url[:55]}`")
                st.markdown(f"**Elements:** {len(page.elements)}")
                st.markdown(f"**Forms:** {len(page.forms)}")
                st.markdown(f"**Tables:** {len(page.tables)}")
                st.markdown(f"**Nav links:** {len(page.nav_links)}")

                ss_path = Path(f"./logs/screenshots/{page.page_name}.png")
                if ss_path.exists():
                    st.image(str(ss_path), caption="Screenshot", use_container_width=True)

            with right:
                if page.elements:
                    counts = Counter(e.element_type for e in page.elements)
                    st.markdown("**Element types:**")
                    tc = st.columns(min(len(counts), 5))
                    for i, (etype, cnt) in enumerate(counts.most_common(5)):
                        tc[i].metric(etype, cnt)

                    st.markdown("**All elements with locators:**")
                    rows = []
                    for el in page.elements:
                        label = (el.label or el.text or el.placeholder
                                 or el.aria_label or el.el_name or el.el_id or "?")[:60]
                        rows.append({
                            "Type":     el.element_type,
                            "Label":    label,
                            "Strategy": el.best_locator_strategy,
                            "Locator":  (el.best_locator or "—")[:80],
                            "Req":      "✓" if el.is_required else "",
                        })
                    st.dataframe(
                        pd.DataFrame(rows),
                        use_container_width=True,
                        height=min(420, len(rows) * 36 + 40),
                    )

                if page.forms:
                    st.markdown("**Form fields:**")
                    for form in page.forms:
                        header = (
                            f"Form: {form.form_id or form.form_name or 'unnamed'} "
                            f"({len(form.fields)} fields)"
                        )
                        with st.expander(header):
                            for f in form.fields:
                                lbl = (f.get("label") or f.get("placeholder")
                                       or f.get("name") or f.get("id") or f.get("type") or "?")
                                st.code(
                                    f"[{f['type'] or f['tag']}]  "
                                    f"label='{lbl}'  "
                                    f"name='{f['name']}'  "
                                    f"id='{f['id']}'  "
                                    f"{'[required]' if f.get('required') else ''}"
                                )

    # Next steps
    st.markdown("---")
    st.info(
        "✅ Complete DOM extraction done. "
        "Proceed to generate **Step Definitions** and **Page Objects** with real locators."
    )
    nc1, nc2, nc3 = st.columns(3)
    with nc1:
        if st.button("→ Step Definitions", type="primary", use_container_width=True):
            st.session_state.page = "Generate Step Definitions"
            st.rerun()
    with nc2:
        if st.button("→ Page Objects", use_container_width=True):
            st.session_state.page = "Generate Page Objects"
            st.rerun()
    with nc3:
        if st.button("→ Package & Run Tests", use_container_width=True):
            st.session_state.page = "Run Tests"
            st.rerun()


def _render_feature_result():
    content  = st.session_state["generated_feature_file"]
    filename = st.session_state.get("feature_file_name", "output.feature")

    st.markdown("---")
    st.markdown("### Generated Feature File")

    dl, clr, info = st.columns([2, 2, 6])
    with dl:
        st.download_button(
            "⬇️ Download .feature",
            data=content.encode(),
            file_name=filename,
            mime="text/plain",
            use_container_width=True,
        )
    with clr:
        if st.button("🗑️ Clear", key="clr_url_feat", use_container_width=True):
            st.session_state.pop("generated_feature_file", None)
            st.rerun()
    with info:
        st.caption(f"{count_scenarios(content)} scenarios · {len(content):,} chars · {filename}")

    st.code(content, language="gherkin", line_numbers=True)


def _default_module(url: str) -> str:
    from urllib.parse import urlparse
    host = urlparse(url).netloc.replace("www.", "")
    return host.split(".")[0].capitalize() + " Application"
