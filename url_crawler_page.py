"""
Module: Web Application Crawler

Accepts a URL + optional credentials, launches a headless Playwright browser,
crawls every reachable page, extracts DOM elements with locators, then feeds
the result into the feature-file generator pipeline.
"""

import json
import time
import threading
import streamlit as st

from config.settings import Settings
from services.azure_openai_service import AzureOpenAIService
from services.chroma_service import ChromaService
from services.web_crawler import WebCrawler, summarize_crawl_for_llm
from services.dom_extractor import elements_to_step_context, pages_to_pom_context
from agents.url_analyzer_agent import URLAnalyzerAgent
from agents.qa_review_agent import QAReviewAgent
from agents.duplicate_detection_agent import DuplicateDetectionAgent
from utils.helpers import count_scenarios, sanitize_filename
from utils.logger import AppLogger

logger = AppLogger.get_logger("page.url_crawler")


def render_url_crawler_page():
    st.markdown("## 🌐 Generate from Web Application")
    st.caption(
        "Provide the URL of your web application. The AI will crawl every page, "
        "extract DOM elements with real locators, then generate feature files, "
        "step definitions, and Page Objects automatically."
    )

    settings = Settings()
    if not settings.is_configured():
        st.error("⚠️ Azure OpenAI is not configured. Go to **Settings** first.")
        return

    # Check Playwright availability
    try:
        import playwright  # noqa: F401
    except ImportError:
        st.error(
            "⚠️ Playwright is not installed.\n\n"
            "Run these commands and restart the app:\n"
            "```\npip install playwright\nplaywright install chromium\n```"
        )
        return

    # ------------------------------------------------------------------ #
    #  Input form                                                          #
    # ------------------------------------------------------------------ #
    with st.form("crawl_form"):
        st.markdown("### 1. Application URL")
        base_url = st.text_input(
            "Web Application URL",
            placeholder="https://your-app.com",
            help="The home page or login page of the app",
        )

        st.markdown("### 2. Authentication (optional)")
        auth_col1, auth_col2 = st.columns(2)
        with auth_col1:
            username = st.text_input("Username / Email", placeholder="admin@company.com")
        with auth_col2:
            password = st.text_input("Password", type="password")

        login_url = st.text_input(
            "Login URL (if different from app URL)",
            placeholder="https://your-app.com/login  — leave blank to use the app URL",
        )

        with st.expander("⚙️ Advanced Crawl Settings"):
            adv1, adv2, adv3 = st.columns(3)
            with adv1:
                max_pages = st.slider("Max pages to crawl", 3, 30, 12)
            with adv2:
                headless = st.checkbox("Headless browser", value=True,
                                       help="Uncheck to watch the browser crawl")
            with adv3:
                module_name = st.text_input("Feature / Module Name",
                                            placeholder="e.g. User Portal")

            st.markdown("**Custom element selectors** (leave blank for auto-detection)")
            s1, s2, s3 = st.columns(3)
            with s1:
                username_sel = st.text_input("Username field CSS", placeholder="input[name='email']")
            with s2:
                password_sel = st.text_input("Password field CSS", placeholder="input[type='password']")
            with s3:
                submit_sel = st.text_input("Submit button CSS", placeholder="button[type='submit']")

        run_qa_review = st.checkbox("Run QA Review Agent after generation", value=True)
        submitted = st.form_submit_button("🚀 Crawl & Generate", type="primary", use_container_width=True)

    if submitted:
        if not base_url.strip():
            st.error("Please enter the application URL.")
            return
        _run_crawl_pipeline(
            base_url=base_url.strip(),
            username=username,
            password=password,
            login_url=(login_url.strip() or base_url.strip()),
            max_pages=max_pages,
            headless=headless,
            module_name=(module_name.strip() or _url_to_module_name(base_url)),
            username_sel=username_sel,
            password_sel=password_sel,
            submit_sel=submit_sel,
            run_qa_review=run_qa_review,
            settings=settings,
        )

    # ------------------------------------------------------------------ #
    #  Results                                                             #
    # ------------------------------------------------------------------ #
    if st.session_state.get("crawl_pages_data"):
        _render_crawl_summary()

    if st.session_state.get("generated_feature_file"):
        _render_feature_result()


# ------------------------------------------------------------------ #
#  Pipeline                                                            #
# ------------------------------------------------------------------ #

def _run_crawl_pipeline(
    base_url, username, password, login_url, max_pages, headless,
    module_name, username_sel, password_sel, submit_sel, run_qa_review, settings
):
    status_box = st.empty()
    progress = st.progress(0, "Initialising crawler…")
    log_box = st.empty()
    logs: list[str] = []

    def log(msg: str, level: str = "INFO"):
        ts = time.strftime("%H:%M:%S")
        logs.append(f"[{level}] {ts}  {msg}")
        if level == "ERROR":
            logger.error(msg)
        else:
            logger.info(msg)
        log_box.code("\n".join(logs[-30:]), language=None)

    try:
        log(f"Starting crawl: {base_url}")
        log(f"Auth: {'yes — ' + username if username else 'none (public app)'}")
        log(f"Max pages: {max_pages} | Headless: {headless}")
        progress.progress(5, "Launching browser…")

        # Crawl
        crawler = WebCrawler(
            base_url=base_url,
            username=username,
            password=password,
            max_pages=max_pages,
            headless=headless,
            username_selector=username_sel,
            password_selector=password_sel,
            submit_selector=submit_sel,
            login_url=login_url,
            progress_callback=log,
        )
        pages = crawler.crawl()
        log(f"Crawl complete: {len(pages)} pages, "
            f"{sum(len(p.elements) for p in pages)} elements extracted")
        progress.progress(40, "Analysing DOM…")

        # Store page data for later use (page objects, step defs)
        st.session_state["crawl_pages_data"] = pages
        st.session_state["crawl_base_url"] = base_url
        st.session_state["crawl_dom_text"] = elements_to_step_context(pages)
        st.session_state["crawl_summary"] = summarize_crawl_for_llm(pages)
        log(f"DOM context built: {len(st.session_state['crawl_dom_text'])} chars")
        progress.progress(50, "Generating feature file…")

        # Feature generation
        log("URLAnalyzerAgent: generating Gherkin from crawl data")
        openai_svc = AzureOpenAIService(settings)
        chroma_svc = ChromaService(settings)

        agent = URLAnalyzerAgent(openai_svc, chroma_svc)
        feature_file = agent.generate(st.session_state["crawl_summary"], module_name)
        log("Feature file draft generated")
        progress.progress(70, "QA review…" if run_qa_review else "Finalising…")

        if run_qa_review:
            log("QAReviewAgent: quality gate review")
            feature_file = QAReviewAgent(openai_svc).review(feature_file)
            log("QA review complete")
        progress.progress(85, "Duplicate check…")

        log("DuplicateDetectionAgent: checking repository")
        dup = DuplicateDetectionAgent(chroma_svc).check_and_store(feature_file)
        log(f"Unique: {dup['unique']} | Duplicates removed: {dup['duplicates']}")
        progress.progress(100, "Done!")

        st.session_state["generated_feature_file"] = feature_file
        st.session_state["feature_file_name"] = sanitize_filename(module_name) + ".feature"
        st.session_state["logs"] = logs

        status_box.success(
            f"✅ Crawled {len(pages)} pages · {count_scenarios(feature_file)} scenarios generated · "
            f"Azure tokens: {openai_svc.total_tokens:,}"
        )

    except Exception as exc:
        log(f"Pipeline error: {exc}", "ERROR")
        logger.error("URL crawl pipeline failed", exc_info=True)
        status_box.error(f"❌ Failed: {exc}")
        progress.empty()


# ------------------------------------------------------------------ #
#  Results panels                                                      #
# ------------------------------------------------------------------ #

def _render_crawl_summary():
    pages = st.session_state.get("crawl_pages_data", [])
    if not pages:
        return

    st.markdown("---")
    st.markdown(f"### 🗺️ Crawl Results — {len(pages)} Pages")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pages crawled", len(pages))
    c2.metric("Total elements", sum(len(p.elements) for p in pages))
    c3.metric("Forms found", sum(len(p.forms) for p in pages))
    c4.metric("Unique links", sum(len(p.all_links) for p in pages))

    with st.expander("📋 View page-by-page breakdown"):
        for page in pages:
            col_a, col_b, col_c = st.columns([4, 1, 1])
            with col_a:
                st.markdown(f"**{page.page_name}** — `{page.url}`")
            with col_b:
                st.caption(f"{len(page.elements)} elements")
            with col_c:
                st.caption(f"{len(page.forms)} forms")

    # Navigation to next step
    st.info(
        "✅ DOM extracted. Now go to **Generate Step Definitions** or "
        "**Generate Page Objects** — the crawl data will be used automatically."
    )
    if st.button("→ Generate Step Definitions & Page Objects", type="primary"):
        st.session_state.page = "Generate Step Definitions"
        st.rerun()


def _render_feature_result():
    st.markdown("---")
    st.markdown("### Generated Feature File")
    content = st.session_state["generated_feature_file"]
    filename = st.session_state.get("feature_file_name", "output.feature")

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
        if st.button("🗑️ Clear", use_container_width=True, key="clr_crawl_feat"):
            st.session_state.pop("generated_feature_file", None)
            st.rerun()
    with info:
        st.caption(f"{count_scenarios(content)} scenarios · {len(content):,} chars · {filename}")

    st.code(content, language="gherkin", line_numbers=True)


def _url_to_module_name(url: str) -> str:
    from urllib.parse import urlparse
    host = urlparse(url).netloc.replace("www.", "")
    return host.split(".")[0].capitalize() + " Application"
