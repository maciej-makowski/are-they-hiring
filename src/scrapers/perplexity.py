from src.scrapers.openai_scraper import OpenAIScraper


class PerplexityScraper(OpenAIScraper):
    company = "perplexity"
    api_url = "https://api.ashbyhq.com/posting-api/job-board/perplexity"
