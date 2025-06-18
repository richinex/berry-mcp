# File: src/ai_agent/tools/scientific_research.py
from typing import List, Dict, Any
import asyncio
import requests
from bs4 import BeautifulSoup
import feedparser
import urllib.parse

# Define base URLs for different scientific sources
SCIENTIFIC_API_BASE_URL = "http://export.arxiv.org/api/query?"
PUBMED_BASE_URL = "https://pubmed.ncbi.nlm.nih.gov"

# Function to scrape data from ArXiv based on the query
async def scrape_arxiv_papers(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    query_string = f"search_query=all:{urllib.parse.quote(query)}&start=0&max_results={max_results}"
    url = SCIENTIFIC_API_BASE_URL + query_string
    feed = feedparser.parse(url)

    results = []
    for entry in feed.entries:
        paper = {
            "title": entry.title,
            "summary": entry.summary,
            "published": entry.published,
            "link": entry.link,
            "doi": entry.get('id', ''),
        }
        results.append(paper)
    return results

# Function to scrape data from PubMed based on the query
async def scrape_pubmed_papers(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    search_url = f"{PUBMED_BASE_URL}/?term={urllib.parse.quote(query)}&size={max_results}"
    response = requests.get(search_url)
    soup = BeautifulSoup(response.content, 'html.parser')

    results = []
    for article in soup.find_all('article', class_='full-docsum'):
        title = article.find('a', class_='docsum-title').text.strip()
        link = f"{PUBMED_BASE_URL}{article.find('a', class_='docsum-title')['href']}"
        summary = article.find('div', class_='full-view-snippet').text.strip() if article.find('div', class_='full-view-snippet') else "No summary available"

        paper = {
            "title": title,
            "summary": summary,
            "link": link,
        }
        results.append(paper)
    return results

# General function to search across multiple sources (arXiv, PubMed)
async def search_scientific_papers(query: str, source: str = 'arxiv', max_results: int = 5) -> List[Dict[str, Any]]:
    if source == 'arxiv':
        return await scrape_arxiv_papers(query, max_results)
    elif source == 'pubmed':
        return await scrape_pubmed_papers(query, max_results)
    else:
        raise ValueError("Unsupported source. Please choose 'arxiv' or 'pubmed'.")

