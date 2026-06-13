from bs4 import BeautifulSoup
import requests

page_to_scrape = requests.get("https://karir.com/search-lowongan?keyword=Business%20Development")
soup = BeautifulSoup(page_to_scrape.text, "html.parser")
job_type = soup.findAll()
