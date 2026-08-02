from google import genai
from pypdf import PdfReader
from config import GEMINI_API_KEY
from bs4 import BeautifulSoup
import re
import requests


class AIEngine:
    def __init__(self, api_key: str = None):
        key = api_key or GEMINI_API_KEY
        self.client = genai.Client(api_key=key)

    def extract_text_from_pdf(self, pdf_file) -> str:
        """Извлекает весь текст из загруженного PDF-файла резюме."""
        try:
            reader = PdfReader(pdf_file)
            text = ""
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
            return text.strip()
        except Exception as e:
            return f"Ошибка при чтении PDF: {e}"

    def match_job_by_keywords(self, job_text: str, keywords: list[str]) -> bool:
        """Быстрая проверка: содержит ли вакансия хотя бы одно ключевое слово."""
        if not keywords:
            return True
        job_lower = job_text.lower()
        return any(kw.lower().strip() in job_lower for kw in keywords if kw.strip())

    def fetch_job_description_from_url(self, text: str) -> str:
        """Ищет ссылки в тексте поста (например, Telegra.ph) и вытаскивает оттуда подробное описание."""
        urls = re.findall(r'https?://[^\s]+', text)
        detailed_text = ""

        for url in urls:
            if "t.me" in url or "telegram.me" in url:
                continue
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                response = requests.get(url, headers=headers, timeout=6)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    content_block = (
                        soup.find('article') or
                        soup.find('div', class_='tl_article_content') or
                        soup.find('div', class_='post-content') or
                        soup.find('main') or
                        soup
                    )
                    page_text = content_block.get_text(separator='\n', strip=True)
                    if page_text:
                        detailed_text += f"\n\n--- Подробный текст из ссылки {url} ---\n{page_text}\n"
            except Exception as e:
                print(f"Не удалось прочитать ссылку {url}: {e}")

        return detailed_text

    def generate_cover_letter(self, base_resume: str, job_text: str, user_instructions: str = "") -> str:
        extra_details = self.fetch_job_description_from_url(job_text)
        full_job_content = job_text + extra_details

        system_instruction = (
            "Ты — профессиональный карьерный ассистент. "
            "Твоя задача — написать убедительное, емкое и естественное сопроводительное письмо на русском языке. "
            "Избегай штампов, излишней воды и пояснений в скобках. Пиши четко, профессионально и по делу."
        )

        user_prompt = f"""
Напиши сопроводительное письмо для отклика на вакансию. Обязательно опирайся на подробное описание вакансии, которое может находиться как в самом тексте поста, так и в тексте, полученном по ссылкам (например, с Telegra.ph).

Пожелания к стилю:
{user_instructions}

Базовое резюме кандидата:
---
{base_resume}
---

Текст вакансии и содержимое по ссылкам:
---
{full_job_content}
---
"""
        try:
            response = self.client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=user_prompt,
                config={
                    "system_instruction": system_instruction,
                    "temperature": 0.7,
                }
            )
            return response.text.strip()
        except Exception as e:
            return f"Ошибка при генерации письма через Gemini: {e}"