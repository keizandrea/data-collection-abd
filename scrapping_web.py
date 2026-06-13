"""
=====================================================================
  Pengumpulan Data Lowongan Kerja - Web Scraping
  Target Platform : Glints, JobStreet, LinkedIn
  Target Roles    : UI/UX Designer, Data Analyst, Fullstack Developer
  Output          : raw_dataset_lowongan.csv  &  raw_dataset_lowongan.json
  Metode          : BeautifulSoup (requests) + Selenium (dynamic page)
=====================================================================
"""

import time
import json
import logging
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException, NoSuchElementException, WebDriverException
    )
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logging.warning("Selenium tidak terinstall. Hanya BeautifulSoup yang digunakan.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

TARGET_ROLES = ["UI/UX Designer", "Data Analyst", "Fullstack Developer"]

OUTPUT_DIR  = Path(".")
OUTPUT_CSV  = OUTPUT_DIR / "raw_dataset_lowongan.csv"
OUTPUT_JSON = OUTPUT_DIR / "raw_dataset_lowongan.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}

# Kolom target raw dataset
COLUMNS = [
    "job_title",
    "company_name",
    "location",
    "job_type",           # Full-time / Part-time / Remote / Contract
    "experience_level",
    "education_req",
    "salary_range",
    "job_requirements",   # Skills / tools
    "responsibilities",
    "posted_date",
    "scraped_date",
    "source_platform",
    "job_url",
]


# ═══════════════════════════════════════════════════════════════════════════
#  HELPER: Selenium driver
# ═══════════════════════════════════════════════════════════════════════════
def build_selenium_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    return driver


def selenium_get(driver, url: str, wait_selector: str, timeout: int = 15) -> BeautifulSoup | None:
    """Buka URL dengan Selenium lalu kembalikan BeautifulSoup dari page source."""
    try:
        driver.get(url)
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
        )
        return BeautifulSoup(driver.page_source, "html.parser")
    except (TimeoutException, WebDriverException) as exc:
        log.warning("Selenium gagal untuk %s: %s", url, exc)
        return None


# ═══════════════════════════════════════════════════════════════════════════
#  SCRAPER 1 — Glints (BeautifulSoup + requests)
# ═══════════════════════════════════════════════════════════════════════════

def scrape_glints(role: str, driver=None) -> list[dict]:
    """
    Glints memakai SSR untuk halaman search sehingga bisa diambil
    dengan requests + BeautifulSoup biasa.
    URL  : https://glints.com/id/opportunities/jobs/explore
    """
    results = []
    keyword = role.replace(" ", "%20")
    url = f"https://glints.com/id/opportunities/jobs/explore?keyword={keyword}&locationName=Indonesia"

    log.info("[Glints] Mencari: '%s'", role)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as exc:
        log.warning("[Glints] requests gagal (%s). Mencoba Selenium...", exc)
        if driver:
            soup = selenium_get(driver, url, "div[data-cy='job-card']")
        else:
            soup = None

    if not soup:
        log.error("[Glints] Tidak bisa memuat halaman untuk '%s'.", role)
        return results

    # Kartu lowongan Glints — selector umum (bisa berubah, perlu validasi ulang)
    cards = soup.select("div[data-cy='job-card'], div.JobCardSC__JobcardContainer, article.JobCard")

    if not cards:
        log.warning("[Glints] Tidak ada kartu ditemukan. Struktur halaman mungkin berubah.")
        # Fallback: coba selector alternatif
        cards = soup.find_all("div", class_=re.compile(r"JobCard|job-card", re.I))

    log.info("[Glints] Ditemukan %d kartu untuk '%s'.", len(cards), role)

    for card in cards:
        try:
            title_el   = card.select_one("h3, h2, [data-cy='job-title']")
            company_el = card.select_one("[data-cy='company-name'], .companyName, p.company")
            loc_el     = card.select_one("[data-cy='job-location'], .location, span.location")
            salary_el  = card.select_one("[data-cy='salary'], .salary, span.salary")
            type_el    = card.select_one("[data-cy='job-type'], .jobType")
            link_el    = card.find("a", href=True)

            entry = {
                "job_title"       : title_el.get_text(strip=True)   if title_el   else role,
                "company_name"    : company_el.get_text(strip=True) if company_el else "N/A",
                "location"        : loc_el.get_text(strip=True)     if loc_el     else "N/A",
                "job_type"        : type_el.get_text(strip=True)    if type_el    else "N/A",
                "experience_level": "N/A",
                "education_req"   : "N/A",
                "salary_range"    : salary_el.get_text(strip=True)  if salary_el  else "Tidak Ditampilkan",
                "job_requirements": "N/A",
                "responsibilities": "N/A",
                "posted_date"     : "N/A",
                "scraped_date"    : date.today().isoformat(),
                "source_platform" : "Glints",
                "job_url"         : (
                    "https://glints.com" + link_el["href"]
                    if link_el and link_el["href"].startswith("/")
                    else (link_el["href"] if link_el else "N/A")
                ),
            }
            results.append(entry)
        except Exception as exc:
            log.debug("[Glints] Gagal parse kartu: %s", exc)

    return results


# ═══════════════════════════════════════════════════════════════════════════
#  SCRAPER 2 — JobStreet (BeautifulSoup + requests / Selenium fallback)
# ═══════════════════════════════════════════════════════════════════════════

def scrape_jobstreet(role: str, driver=None) -> list[dict]:
    """
    JobStreet Indonesia — halaman search biasanya server-rendered
    URL : https://www.jobstreet.co.id/jobs/<keyword>
    """
    results = []
    keyword = role.lower().replace(" ", "-")
    url = f"https://www.jobstreet.co.id/jobs/{keyword}"

    log.info("[JobStreet] Mencari: '%s'", role)

    soup = None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as exc:
        log.warning("[JobStreet] requests gagal (%s). Mencoba Selenium...", exc)

    # Beberapa halaman JobStreet butuh JS — pakai Selenium
    if (not soup or not soup.select("article[data-job-id]")) and driver:
        soup = selenium_get(driver, url, "article[data-job-id]")

    if not soup:
        log.error("[JobStreet] Tidak bisa memuat halaman untuk '%s'.", role)
        return results

    cards = soup.select("article[data-job-id], div[data-automation='jobListing']")

    if not cards:
        log.warning("[JobStreet] Tidak ada kartu ditemukan.")
        cards = soup.find_all("article") or soup.find_all("div", {"data-automation": True})

    log.info("[JobStreet] Ditemukan %d kartu untuk '%s'.", len(cards), role)

    for card in cards:
        try:
            title_el   = card.select_one("h1, h3, [data-automation='jobTitle']")
            company_el = card.select_one("[data-automation='jobCompany'], .company")
            loc_el     = card.select_one("[data-automation='jobLocation'], .location")
            salary_el  = card.select_one("[data-automation='jobSalary'], .salary")
            date_el    = card.select_one("time, [data-automation='jobListingDate']")
            link_el    = card.find("a", href=True)

            job_url = ""
            if link_el:
                href = link_el["href"]
                job_url = href if href.startswith("http") else "https://www.jobstreet.co.id" + href

            entry = {
                "job_title"       : title_el.get_text(strip=True)   if title_el   else role,
                "company_name"    : company_el.get_text(strip=True) if company_el else "N/A",
                "location"        : loc_el.get_text(strip=True)     if loc_el     else "N/A",
                "job_type"        : "N/A",
                "experience_level": "N/A",
                "education_req"   : "N/A",
                "salary_range"    : salary_el.get_text(strip=True)  if salary_el  else "Tidak Ditampilkan",
                "job_requirements": "N/A",
                "responsibilities": "N/A",
                "posted_date"     : date_el.get_text(strip=True) if date_el else "N/A",
                "scraped_date"    : date.today().isoformat(),
                "source_platform" : "JobStreet",
                "job_url"         : job_url,
            }
            results.append(entry)
        except Exception as exc:
            log.debug("[JobStreet] Gagal parse kartu: %s", exc)

    return results


# ═══════════════════════════════════════════════════════════════════════════
#  SCRAPER 3 — LinkedIn (Selenium; perlu login untuk hasil penuh)
# ═══════════════════════════════════════════════════════════════════════════

def scrape_linkedin(role: str, driver=None) -> list[dict]:
    """
    LinkedIn public job search (tanpa login).
    URL : https://www.linkedin.com/jobs/search/
    Catatan: LinkedIn bisa memblokir request tanpa cookie. Gunakan Selenium
             dan pertimbangkan delay antar request.
    """
    results = []

    if not driver:
        log.warning("[LinkedIn] Selenium diperlukan untuk LinkedIn. Dilewati.")
        return results

    keyword = role.replace(" ", "%20")
    url = (
        f"https://www.linkedin.com/jobs/search/"
        f"?keywords={keyword}&location=Indonesia&f_TPR=r86400"
    )

    log.info("[LinkedIn] Mencari: '%s'", role)
    soup = selenium_get(driver, url, "ul.jobs-search__results-list, div.job-search-card", timeout=20)

    if not soup:
        log.error("[LinkedIn] Tidak bisa memuat halaman untuk '%s'.", role)
        return results

    cards = soup.select("li.jobs-search__results-list-item, div.job-search-card")
    log.info("[LinkedIn] Ditemukan %d kartu untuk '%s'.", len(cards), role)

    for card in cards:
        try:
            title_el   = card.select_one("h3.base-search-card__title, h3")
            company_el = card.select_one("h4.base-search-card__subtitle, h4")
            loc_el     = card.select_one("span.job-search-card__location, .job-search-card__location")
            date_el    = card.select_one("time")
            link_el    = card.find("a", href=True)

            entry = {
                "job_title"       : title_el.get_text(strip=True)   if title_el   else role,
                "company_name"    : company_el.get_text(strip=True) if company_el else "N/A",
                "location"        : loc_el.get_text(strip=True)     if loc_el     else "N/A",
                "job_type"        : "N/A",
                "experience_level": "N/A",
                "education_req"   : "N/A",
                "salary_range"    : "Tidak Ditampilkan",
                "job_requirements": "N/A",
                "responsibilities": "N/A",
                "posted_date"     : date_el.get("datetime", "N/A") if date_el else "N/A",
                "scraped_date"    : date.today().isoformat(),
                "source_platform" : "LinkedIn",
                "job_url"         : link_el["href"].split("?")[0] if link_el else "N/A",
            }
            results.append(entry)
        except Exception as exc:
            log.debug("[LinkedIn] Gagal parse kartu: %s", exc)

    return results


# ═══════════════════════════════════════════════════════════════════════════
#  DETAIL SCRAPER — Kunjungi URL tiap lowongan untuk data lebih lengkap
# ═══════════════════════════════════════════════════════════════════════════

def enrich_job_detail_glints(entry: dict, driver=None) -> dict:
    """
    Kunjungi halaman detail Glints untuk mengambil requirements & responsibilities.
    """
    if entry["job_url"] in ("N/A", ""):
        return entry

    soup = None
    try:
        resp = requests.get(entry["job_url"], headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        if driver:
            soup = selenium_get(driver, entry["job_url"], "div.JobDescription")

    if not soup:
        return entry

    # Glints: bagian deskripsi pekerjaan
    desc_el = soup.select_one(
        "div.JobDescription, div[data-cy='job-detail-description'], section.jd-section"
    )
    if desc_el:
        full_text = desc_el.get_text("\n", strip=True)

        # Pisahkan requirements & responsibilities dari teks bebas
        req_match = re.search(
            r"(requirement|kualifikasi|persyaratan)(.*?)(responsibilit|tanggung jawab|deskripsi|$)",
            full_text, re.I | re.S
        )
        resp_match = re.search(
            r"(responsibilit|tanggung jawab|job desc)(.*?)(requirement|kualifikasi|$)",
            full_text, re.I | re.S
        )

        if req_match:
            entry["job_requirements"] = req_match.group(2).strip()[:500]
        if resp_match:
            entry["responsibilities"] = resp_match.group(2).strip()[:500]

    # Experience & education
    exp_el = soup.select_one("[data-cy='experience'], .experience, span.exp")
    edu_el = soup.select_one("[data-cy='education'], .education, span.edu")
    type_el = soup.select_one("[data-cy='job-type'], .jobType")

    if exp_el:
        entry["experience_level"] = exp_el.get_text(strip=True)
    if edu_el:
        entry["education_req"] = edu_el.get_text(strip=True)
    if type_el:
        entry["job_type"] = type_el.get_text(strip=True)

    return entry


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════

def main():
    log.info("=" * 60)
    log.info("  Mulai Scraping Lowongan Kerja")
    log.info("  Tanggal: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 60)

    # Inisialisasi Selenium (opsional)
    driver = build_selenium_driver()
    if driver:
        log.info("Selenium Chrome driver berhasil dibuat.")
    else:
        log.info("Berjalan tanpa Selenium (hanya BeautifulSoup).")

    all_results: list[dict] = []

    for role in TARGET_ROLES:
        log.info("\n── Role: %s ──", role)

        # ── Glints ──────────────────────────────────────────────────────
        glints_data = scrape_glints(role, driver)
        log.info("[Glints] %d lowongan ditemukan.", len(glints_data))

        # Enrich detail untuk 3 entry pertama (hemat waktu & bandwidth)
        enriched = []
        for i, entry in enumerate(glints_data[:3]):
            log.info("  Enriching Glints entry %d/%d: %s", i+1, min(3, len(glints_data)), entry["job_title"])
            enriched.append(enrich_job_detail_glints(entry, driver))
            time.sleep(1.5)  # jeda sopan
        all_results.extend(enriched + glints_data[3:])

        time.sleep(2)

        # ── JobStreet ────────────────────────────────────────────────────
        js_data = scrape_jobstreet(role, driver)
        log.info("[JobStreet] %d lowongan ditemukan.", len(js_data))
        all_results.extend(js_data)

        time.sleep(2)

        # ── LinkedIn ─────────────────────────────────────────────────────
        li_data = scrape_linkedin(role, driver)
        log.info("[LinkedIn] %d lowongan ditemukan.", len(li_data))
        all_results.extend(li_data)

        time.sleep(3)

    # ── Tutup driver ─────────────────────────────────────────────────────
    if driver:
        driver.quit()
        log.info("Selenium driver ditutup.")

    # ── Simpan output ─────────────────────────────────────────────────────
    if not all_results:
        log.error("Tidak ada data yang berhasil dikumpulkan. Cek koneksi atau selector.")
        return

    df = pd.DataFrame(all_results, columns=COLUMNS)

    # Bersihkan whitespace berlebih
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()

    # Hapus duplikat (job_title + company_name + source)
    before = len(df)
    df.drop_duplicates(subset=["job_title", "company_name", "source_platform"], inplace=True)
    log.info("Duplikat dihapus: %d → %d baris.", before, len(df))

    # Simpan CSV
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    log.info("CSV tersimpan → %s", OUTPUT_CSV)

    # Simpan JSON
    df.to_json(OUTPUT_JSON, orient="records", force_ascii=False, indent=2)
    log.info("JSON tersimpan → %s", OUTPUT_JSON)

    # ── Ringkasan ────────────────────────────────────────────────────────
    log.info("\n%s", "=" * 60)
    log.info("RINGKASAN RAW DATASET")
    log.info("Total lowongan  : %d", len(df))
    log.info("Per platform    :")
    for platform, count in df["source_platform"].value_counts().items():
        log.info("  %-12s: %d", platform, count)
    log.info("Per role        :")
    # Cocokkan job_title ke TARGET_ROLES
    for role in TARGET_ROLES:
        n = df["job_title"].str.contains(role.split()[0], case=False, na=False).sum()
        log.info("  %-30s: %d", role, n)
    log.info("Output CSV  → %s", OUTPUT_CSV.resolve())
    log.info("Output JSON → %s", OUTPUT_JSON.resolve())
    log.info("=" * 60)


if __name__ == "__main__":
    main()