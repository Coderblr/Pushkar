from services.azure_openai_service import AzureOpenAIService
from services.chroma_service import ChromaService
from prompts.url_analysis_prompt import SYSTEM, USER_TEMPLATE
from utils.helpers import clean_gherkin_output
from utils.logger import AppLogger

logger = AppLogger.get_logger("agent.url_analyzer")


class URLAnalyzerAgent:
    """
    Generates a Gherkin feature file directly from web-crawl DOM data.
    Input: summarised crawl text (from summarize_crawl_for_llm).
    Output: raw Gherkin feature file content.
    """

    def __init__(self, openai_service: AzureOpenAIService, chroma_service: ChromaService):
        self.svc = openai_service
        self.chroma = chroma_service

    def generate(self, crawl_summary: str, module_name: str = "Application") -> str:
        logger.info(f"URLAnalyzerAgent: generating feature for '{module_name}'")

        similar = self.chroma.search_similar_features(crawl_summary[:500], n=3)
        existing = "\n\n---\n".join(s["document"] for s in similar) if similar else "None."

        user_msg = USER_TEMPLATE.format(
            crawl_summary=crawl_summary,
            module_name=module_name,
            existing_scenarios=existing,
        )

        logger.info("Calling Azure OpenAI with crawl data for feature generation")
        raw = self.svc.chat_completion(
            messages=[{"role": "user", "content": user_msg}],
            system_prompt=SYSTEM,
            temperature=0.4,
            max_tokens=4000,
        )
        result = clean_gherkin_output(raw)
        logger.info("URLAnalyzerAgent: feature file generated")
        return result
