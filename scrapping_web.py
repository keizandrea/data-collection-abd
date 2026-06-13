"""
=====================================================================
  Pengumpulan Data Lowongan Kerja - Web Scraping
  Target Platform : LinkedIn (public), Glints, JobStreet
  Target Roles    : UI/UX Designer, Data Analyst, Fullstack Developer
  Output          : raw_dataset_lowongan.csv  &  raw_dataset_lowongan.json
  Metode          : Selenium (headless Chrome)
=====================================================================
"""

import time
import logging
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

try:
    from webdriver_manager.chrome import ChromeDriverManager
    USE_WDM = True
except ImportError:
    USE_WDM = False

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Konfigurasi ──────────────────────────────────────────────────────────────
TARGET_ROLES = ["UI/UX Designer", "Data Analyst", "Fullstack Developer"]

OUTPUT_CSV  = Path("raw_dataset_lowongan.csv")
OUTPUT_JSON = Path("raw_dataset_lowongan.json")

COLUMNS = [
    "job_title", "company_name", "location", "job_type",
    "experience_level", "education_req", "salary_range",
    "job_requirements", "responsibilities",
    "posted_date", "scraped_date", "source_platform", "job_url",
]


# ═══════════════════════════════════════════════════════════════════════════
#  SELENIUM DRIVER
# ═══════════════════════════════════════════════════════════════════════════

def build_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=id-ID")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    # Sembunyikan tanda automation
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    if USE_WDM:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=options
        )
    else:
        driver = webdriver.Chrome(options=options)

    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def wait_and_get(driver, url, css_selector, timeout=20):
    """Buka URL dan tunggu sampai elemen muncul."""
    try:
        driver.get(url)
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
        )
        return True
    except TimeoutException:
        log.warning("Timeout menunggu '%s' di %s", css_selector, url)
        return False


def safe_text(driver, css, default="N/A"):
    """Ambil teks elemen, return default kalau tidak ada."""
    try:
        el = driver.find_element(By.CSS_SELECTOR, css)
        return el.text.strip() or default
    except Exception:
        return default


def safe_texts(driver, css):
    """Ambil semua teks dari semua elemen yang cocok."""
    try:
        els = driver.find_elements(By.CSS_SELECTOR, css)
        return [e.text.strip() for e in els if e.text.strip()]
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════════
#  SCRAPER: LinkedIn
# ═══════════════════════════════════════════════════════════════════════════

def scrape_linkedin(driver, role):
    results = []
    keyword = role.replace(" ", "%20")
    # Filter Indonesia, posted last 30 days
    url = (
        f"https://www.linkedin.com/jobs/search/"
        f"?keywords={keyword}&location=Indonesia&f_TPR=r2592000&f_WT=1%2C2%2C3"
    )

    log.info("[LinkedIn] Mencari: '%s'", role)
    ok = wait_and_get(driver, url, "ul.jobs-search__results-list, div.job-search-card", timeout=25)
    if not ok:
        log.warning("[LinkedIn] Halaman tidak termuat untuk '%s'", role)
        return results

    time.sleep(3)  # tunggu JS selesai

    # Scroll untuk load lebih banyak kartu
    for _ in range(3):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)

    cards = driver.find_elements(By.CSS_SELECTOR,
        "li.jobs-search__results-list-item, div.job-search-card"
    )
    log.info("[LinkedIn] %d kartu ditemukan untuk '%s'", len(cards), role)

    for card in cards:
        try:
            title   = card.find_element(By.CSS_SELECTOR, "h3, .base-search-card__title").text.strip()
            company = card.find_element(By.CSS_SELECTOR, "h4, .base-search-card__subtitle").text.strip()
            loc     = card.find_element(By.CSS_SELECTOR, ".job-search-card__location").text.strip()
            try:
                posted = card.find_element(By.CSS_SELECTOR, "time").get_attribute("datetime")
            except Exception:
                posted = "N/A"
            try:
                link = card.find_element(By.CSS_SELECTOR, "a").get_attribute("href").split("?")[0]
            except Exception:
                link = "N/A"

            results.append({
                "job_title": title, "company_name": company, "location": loc,
                "job_type": "N/A", "experience_level": "N/A", "education_req": "N/A",
                "salary_range": "Tidak Ditampilkan", "job_requirements": "N/A",
                "responsibilities": "N/A", "posted_date": posted,
                "scraped_date": date.today().isoformat(),
                "source_platform": "LinkedIn", "job_url": link,
            })
        except Exception as e:
            log.debug("[LinkedIn] Skip kartu: %s", e)

    return results


def enrich_linkedin(driver, entry):
    """
    Kunjungi halaman detail LinkedIn untuk ambil job_type,
    experience_level, dan job_requirements.
    """
    if entry["job_url"] == "N/A":
        return entry

    try:
        driver.get(entry["job_url"])
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR,
                "div.description__text, div.show-more-less-html"
            ))
        )
        time.sleep(2)

        # Klik "Show more" kalau ada
        try:
            btn = driver.find_element(By.CSS_SELECTOR,
                "button.show-more-less-html__button--more, button[aria-label='Show more']"
            )
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(1)
        except Exception:
            pass

        # Kriteria pekerjaan (job type, seniority, dll)
        criteria_items = driver.find_elements(By.CSS_SELECTOR,
            "li.description__job-criteria-item"
        )
        for item in criteria_items:
            try:
                label = item.find_element(By.CSS_SELECTOR, "h3").text.strip().lower()
                value = item.find_element(By.CSS_SELECTOR, "span").text.strip()
                if "employment" in label or "type" in label or "jenis" in label:
                    entry["job_type"] = value
                elif "seniority" in label or "level" in label or "pengalaman" in label:
                    entry["experience_level"] = value
                elif "education" in label or "pendidikan" in label:
                    entry["education_req"] = value
            except Exception:
                pass

        # Deskripsi / requirements
        try:
            desc_el = driver.find_element(By.CSS_SELECTOR,
                "div.show-more-less-html__markup, div.description__text"
            )
            full_text = desc_el.text.strip()

            # Pisah requirements dari full deskripsi
            req_match = re.search(
                r"(qualif|requirement|kualif|persyaratan|skill)(.*?)"
                r"(responsib|tanggung|benefit|about|tentang|$)",
                full_text, re.I | re.S
            )
            resp_match = re.search(
                r"(responsib|tanggung jawab|job desc|deskripsi pekerjaan)(.*?)"
                r"(qualif|requirement|kualif|benefit|$)",
                full_text, re.I | re.S
            )

            if req_match:
                entry["job_requirements"] = req_match.group(2).strip()[:600]
            elif full_text:
                # Kalau tidak ada section khusus, ambil 400 karakter pertama
                entry["job_requirements"] = full_text[:400]

            if resp_match:
                entry["responsibilities"] = resp_match.group(2).strip()[:600]

        except Exception:
            pass

        # Gaji (kadang muncul di detail)
        try:
            salary = driver.find_element(By.CSS_SELECTOR,
                ".compensation__salary, .salary"
            ).text.strip()
            if salary:
                entry["salary_range"] = salary
        except Exception:
            pass

    except Exception as e:
        log.debug("[LinkedIn] Gagal enrich %s: %s", entry["job_url"], e)

    return entry


# ═══════════════════════════════════════════════════════════════════════════
#  SCRAPER: Glints
# ═══════════════════════════════════════════════════════════════════════════

def scrape_glints(driver, role):
    results = []
    keyword = role.replace(" ", "%20")
    url = (
        f"https://glints.com/id/opportunities/jobs/explore"
        f"?keyword={keyword}&locationName=Indonesia&country=ID"
    )

    log.info("[Glints] Mencari: '%s'", role)

    try:
        driver.get(url)
        # Tunggu salah satu selector yang mungkin muncul
        WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.CSS_SELECTOR,
                "div[class*='JobCardSC'], div[class*='CompactOpportunityCard'], "
                "div[class*='GlintsContainer'] a[href*='/opportunities/jobs']"
            ))
        )
        time.sleep(3)
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)
    except TimeoutException:
        log.warning("[Glints] Timeout untuk '%s'", role)
        return results

    # Coba beberapa selector kartu
    cards = driver.find_elements(By.CSS_SELECTOR,
        "div[class*='JobCardSC__JobcardContainer'], "
        "div[class*='CompactOpportunityCard'], "
        "div[class*='JobCard']"
    )

    # Fallback: ambil semua link lowongan
    if not cards:
        log.warning("[Glints] Selector kartu tidak cocok, coba fallback link...")
        links = driver.find_elements(By.CSS_SELECTOR,
            "a[href*='/opportunities/jobs/']"
        )
        log.info("[Glints] %d link ditemukan (fallback)", len(links))
        for link_el in links[:15]:
            try:
                href = link_el.get_attribute("href")
                title_el = link_el.find_elements(By.CSS_SELECTOR, "h2, h3, span[class*='title']")
                title = title_el[0].text.strip() if title_el else role
                if not title or len(title) < 3:
                    continue
                results.append({
                    "job_title": title, "company_name": "N/A", "location": "N/A",
                    "job_type": "N/A", "experience_level": "N/A", "education_req": "N/A",
                    "salary_range": "N/A", "job_requirements": "N/A",
                    "responsibilities": "N/A", "posted_date": "N/A",
                    "scraped_date": date.today().isoformat(),
                    "source_platform": "Glints", "job_url": href,
                })
            except Exception:
                pass
        return results

    log.info("[Glints] %d kartu ditemukan untuk '%s'", len(cards), role)

    for card in cards:
        try:
            title_el   = card.find_elements(By.CSS_SELECTOR, "h2, h3, [class*='Title']")
            company_el = card.find_elements(By.CSS_SELECTOR, "[class*='company'], [class*='Company']")
            loc_el     = card.find_elements(By.CSS_SELECTOR, "[class*='location'], [class*='Location']")
            salary_el  = card.find_elements(By.CSS_SELECTOR, "[class*='salary'], [class*='Salary']")
            link_el    = card.find_elements(By.CSS_SELECTOR, "a[href]")

            title   = title_el[0].text.strip()   if title_el   else role
            company = company_el[0].text.strip()  if company_el else "N/A"
            loc     = loc_el[0].text.strip()      if loc_el     else "N/A"
            salary  = salary_el[0].text.strip()   if salary_el  else "Tidak Ditampilkan"
            href    = link_el[0].get_attribute("href") if link_el else "N/A"

            if not title or len(title) < 3:
                continue

            results.append({
                "job_title": title, "company_name": company, "location": loc,
                "job_type": "N/A", "experience_level": "N/A", "education_req": "N/A",
                "salary_range": salary, "job_requirements": "N/A",
                "responsibilities": "N/A", "posted_date": "N/A",
                "scraped_date": date.today().isoformat(),
                "source_platform": "Glints", "job_url": href,
            })
        except Exception as e:
            log.debug("[Glints] Skip kartu: %s", e)

    return results


# ═══════════════════════════════════════════════════════════════════════════
#  SCRAPER: JobStreet
# ═══════════════════════════════════════════════════════════════════════════

def scrape_jobstreet(driver, role):
    results = []
    keyword = role.replace(" ", "-").lower()
    url = f"https://www.jobstreet.co.id/jobs/{keyword}-jobs"

    log.info("[JobStreet] Mencari: '%s'", role)

    try:
        driver.get(url)
        WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.CSS_SELECTOR,
                "article[data-job-id], div[data-automation='jobListing'], "
                "div[data-testid='job-card']"
            ))
        )
        time.sleep(3)
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)
    except TimeoutException:
        log.warning("[JobStreet] Timeout untuk '%s'", role)
        return results

    cards = driver.find_elements(By.CSS_SELECTOR,
        "article[data-job-id], div[data-automation='jobListing'], div[data-testid='job-card']"
    )
    log.info("[JobStreet] %d kartu ditemukan untuk '%s'", len(cards), role)

    for card in cards:
        try:
            title_el   = card.find_elements(By.CSS_SELECTOR,
                "h1, h3, [data-automation='jobTitle'], [data-testid='job-title']")
            company_el = card.find_elements(By.CSS_SELECTOR,
                "[data-automation='jobCompany'], [data-testid='company-name'], .company")
            loc_el     = card.find_elements(By.CSS_SELECTOR,
                "[data-automation='jobLocation'], [data-testid='job-location'], .location")
            salary_el  = card.find_elements(By.CSS_SELECTOR,
                "[data-automation='jobSalary'], [data-testid='job-salary']")
            date_el    = card.find_elements(By.CSS_SELECTOR, "time, [data-automation='jobListingDate']")
            link_el    = card.find_elements(By.CSS_SELECTOR, "a[href]")

            title   = title_el[0].text.strip()   if title_el   else role
            company = company_el[0].text.strip()  if company_el else "N/A"
            loc     = loc_el[0].text.strip()      if loc_el     else "N/A"
            salary  = salary_el[0].text.strip()   if salary_el  else "Tidak Ditampilkan"
            posted  = date_el[0].text.strip()     if date_el    else "N/A"

            href = "N/A"
            if link_el:
                href = link_el[0].get_attribute("href")
                if href and not href.startswith("http"):
                    href = "https://www.jobstreet.co.id" + href

            if not title or len(title) < 3:
                continue

            results.append({
                "job_title": title, "company_name": company, "location": loc,
                "job_type": "N/A", "experience_level": "N/A", "education_req": "N/A",
                "salary_range": salary, "job_requirements": "N/A",
                "responsibilities": "N/A", "posted_date": posted,
                "scraped_date": date.today().isoformat(),
                "source_platform": "JobStreet", "job_url": href,
            })
        except Exception as e:
            log.debug("[JobStreet] Skip kartu: %s", e)

    return results


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    log.info("=" * 60)
    log.info("  Scraping Lowongan Kerja — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 60)

    driver = build_driver()
    all_results = []

    try:
        for role in TARGET_ROLES:
            log.info("\n▶ Role: %s", role)

            # LinkedIn — enrich 5 entri pertama
            li_data = scrape_linkedin(driver, role)
            for i, entry in enumerate(li_data[:5]):
                log.info("  Enrich LinkedIn %d/%d: %s", i+1, min(5, len(li_data)), entry["job_title"])
                li_data[i] = enrich_linkedin(driver, entry)
                time.sleep(2)
            all_results.extend(li_data)
            time.sleep(3)

            # Glints
            glints_data = scrape_glints(driver, role)
            all_results.extend(glints_data)
            time.sleep(3)

            # JobStreet
            js_data = scrape_jobstreet(driver, role)
            all_results.extend(js_data)
            time.sleep(3)

    finally:
        driver.quit()
        log.info("Driver ditutup.")

    if not all_results:
        log.error("Tidak ada data yang berhasil dikumpulkan.")
        return

    df = pd.DataFrame(all_results, columns=COLUMNS)

    # Bersihkan
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()

    # Hapus baris tanpa judul valid
    df = df[df["job_title"].str.len() > 3]

    # Deduplikasi
    before = len(df)
    df.drop_duplicates(subset=["job_title", "company_name", "source_platform"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    log.info("Duplikat dihapus: %d → %d baris", before, len(df))

    # Simpan
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    df.to_json(OUTPUT_JSON, orient="records", force_ascii=False, indent=2)

    # Ringkasan
    log.info("\n%s", "=" * 60)
    log.info("RINGKASAN")
    log.info("Total : %d lowongan", len(df))
    for platform, n in df["source_platform"].value_counts().items():
        log.info("  %-12s: %d", platform, n)
    log.info("Output → %s", OUTPUT_CSV.resolve())
    log.info("=" * 60)


if __name__ == "__main__":
    main()