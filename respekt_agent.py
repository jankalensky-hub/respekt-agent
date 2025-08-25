#!/usr/bin/env python3
"""
Respekt EPUB Downloader pro GitHub Actions
Automaticky stáhne aktuální číslo Respektu a odešle na Kindle
"""

import os
import time
import smtplib
import requests
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import logging

# Konfigurace
RESPEKT_LOGIN = os.getenv('RESPEKT_LOGIN')
RESPEKT_PASSWORD = os.getenv('RESPEKT_PASSWORD')
GMAIL_EMAIL = os.getenv('GMAIL_EMAIL')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD')
KINDLE_EMAIL = os.getenv('KINDLE_EMAIL')

# Nastavení logování
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('respekt.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class RespektDownloader:
    def __init__(self):
        self.driver = None
        self.setup_browser()
    
    def setup_browser(self):
        """Nastaví Chrome pro headless mode s optimalizací pro GitHub Actions"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
        
        # Disable images and CSS pro rychlejší načítání
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.managed_default_content_settings.stylesheets": 2
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)
    
    def login(self):
        """Přihlášení na Respekt.cz"""
        try:
            logger.info("Přihlašuji se na Respekt.cz...")
            self.driver.get("https://www.respekt.cz/prihlaseni")
            
            # Počkej na načtení formuláře
            email_field = self.wait.until(
                EC.presence_of_element_located((By.NAME, "email"))
            )
            
            password_field = self.driver.find_element(By.NAME, "password")
            
            # Vyplň přihlašovací údaje
            email_field.clear()
            email_field.send_keys(RESPEKT_LOGIN)
            password_field.clear()
            password_field.send_keys(RESPEKT_PASSWORD)
            
            # Klikni na přihlášení
            login_button = self.driver.find_element(By.XPATH, "//button[@type='submit' or contains(@class, 'login') or contains(text(), 'Přihlásit')]")
            login_button.click()
            
            # Počkej na přesměrování po přihlášení
            time.sleep(3)
            
            # Zkontroluj, zda jsme přihlášeni (hledej nějaký element, který je viditelný jen po přihlášení)
            try:
                # Můžeme hledat odkaz na "Můj účet" nebo podobné
                self.wait.until(
                    EC.any_of(
                        EC.presence_of_element_located((By.XPATH, "//a[contains(@href, 'muj-ucet') or contains(text(), 'Můj účet')]")),
                        EC.presence_of_element_located((By.XPATH, "//a[contains(@href, 'archiv') or contains(text(), 'Archiv')]"))
                    )
                )
                logger.info("Přihlášení úspěšné!")
                return True
            except TimeoutException:
                logger.error("Přihlášení se nezdařilo - nenašel jsem prvky pro přihlášeného uživatele")
                return False
                
        except Exception as e:
            logger.error(f"Chyba při přihlašování: {e}")
            return False
    
    def find_current_issue(self):
        """Najde a stáhne aktuální číslo z archivu"""
        try:
            logger.info("Hledám aktuální číslo v archivu...")
            
            # Jdi do archivu
            self.driver.get("https://www.respekt.cz/archiv")
            time.sleep(3)
            
            # Najdi nejnovější číslo - obvykle je první v seznamu
            # Hledáme odkazy na jednotlivá čísla
            issue_links = self.driver.find_elements(By.XPATH, "//a[contains(@href, '/tydenik/') and contains(@href, '/cislo-')]")
            
            if not issue_links:
                # Alternativní selektory
                issue_links = self.driver.find_elements(By.XPATH, "//a[contains(@href, 'cislo') or contains(@href, 'vydani')]")
            
            if not issue_links:
                logger.error("Nenašel jsem žádné odkazy na čísla časopisu")
                return None
            
            # Vezmi první (nejnovější) číslo
            latest_issue = issue_links[0]
            issue_url = latest_issue.get_attribute('href')
            issue_text = latest_issue.text.strip()
            
            logger.info(f"Nalezeno nejnovější číslo: {issue_text}")
            logger.info(f"URL: {issue_url}")
            
            return issue_url
            
        except Exception as e:
            logger.error(f"Chyba při hledání aktuálního čísla: {e}")
            return None
    
    def download_epub(self, issue_url):
        """Stáhne EPUB z dané stránky čísla"""
        try:
            logger.info(f"Otevírám stránku čísla: {issue_url}")
            self.driver.get(issue_url)
            time.sleep(3)
            
            # Hledej odkaz na EPUB stažení
            epub_selectors = [
                "//a[contains(@href, '.epub')]",
                "//a[contains(text(), 'EPUB')]",
                "//a[contains(text(), 'epub')]",
                "//a[contains(@class, 'epub')]",
                "//a[contains(@href, 'epub')]",
                "//a[contains(text(), 'Stáhnout') and contains(text(), 'EPUB')]"
            ]
            
            epub_link = None
            for selector in epub_selectors:
                try:
                    epub_elements = self.driver.find_elements(By.XPATH, selector)
                    if epub_elements:
                        epub_link = epub_elements[0]
                        break
                except:
                    continue
            
            if not epub_link:
                logger.error("Nenašel jsem odkaz na EPUB stažení")
                return None
            
            epub_url = epub_link.get_attribute('href')
            logger.info(f"Nalezen EPUB odkaz: {epub_url}")
            
            # Stáhni EPUB pomocí session s cookies z prohlížeče
            cookies = self.driver.get_cookies()
            session = requests.Session()
            
            for cookie in cookies:
                session.cookies.set(cookie['name'], cookie['value'])
            
            # Nastav stejné headers jako prohlížeč
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = session.get(epub_url, headers=headers)
            response.raise_for_status()
            
            # Vytvoř název souboru
            today = datetime.now().strftime("%Y-%m-%d")
            filename = f"respekt_{today}.epub"
            
            with open(filename, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"EPUB úspěšně stažen: {filename} ({len(response.content)} bytes)")
            return filename
            
        except Exception as e:
            logger.error(f"Chyba při stahování EPUB: {e}")
            return None
    
    def send_to_kindle(self, epub_file):
        """Odešle EPUB na Kindle"""
        try:
            logger.info(f"Odesílám {epub_file} na Kindle ({KINDLE_EMAIL})...")
            
            # Vytvoř email zprávu
            msg = MIMEMultipart()
            msg['From'] = GMAIL_EMAIL
            msg['To'] = KINDLE_EMAIL
            msg['Subject'] = f"Respekt - {datetime.now().strftime('%d.%m.%Y')}"
            
            # Připoj EPUB soubor
            with open(epub_file, "rb") as attachment:
                part = MIMEBase('application', 'epub+zip')
                part.set_payload(attachment.read())
            
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename="{epub_file}"'
            )
            msg.attach(part)
            
            # Pošli email
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
                server.send_message(msg)
            
            logger.info("Email úspěšně odeslán!")
            return True
            
        except Exception as e:
            logger.error(f"Chyba při odesílání emailu: {e}")
            return False
    
    def run(self):
        """Hlavní metoda - spustí celý proces"""
        try:
            logger.info("=== Spouštím Respekt EPUB Downloader ===")
            
            # Kontrola proměnných prostředí
            required_vars = ['RESPEKT_LOGIN', 'RESPEKT_PASSWORD', 'GMAIL_EMAIL', 'GMAIL_APP_PASSWORD', 'KINDLE_EMAIL']
            missing_vars = [var for var in required_vars if not os.getenv(var)]
            
            if missing_vars:
                logger.error(f"Chybí proměnné prostředí: {', '.join(missing_vars)}")
                return False
            
            # 1. Přihlášení
            if not self.login():
                return False
            
            # 2. Najdi aktuální číslo
            issue_url = self.find_current_issue()
            if not issue_url:
                return False
            
            # 3. Stáhni EPUB
            epub_file = self.download_epub(issue_url)
            if not epub_file:
                return False
            
            # 4. Odešli na Kindle
            success = self.send_to_kindle(epub_file)
            
            if success:
                logger.info("=== Proces úspěšně dokončen! ===")
                # Smaž místní soubor
                try:
                    os.remove(epub_file)
                    logger.info(f"Místní soubor {epub_file} smazán")
                except:
                    pass
            
            return success
            
        except Exception as e:
            logger.error(f"Neočekávaná chyba: {e}")
            return False
        
        finally:
            if self.driver:
                self.driver.quit()

def main():
    """Hlavní funkce"""
    downloader = RespektDownloader()
    success = downloader.run()
    
    if not success:
        exit(1)  # GitHub Actions ukáže jako failed
    
    logger.info("Hotovo!")

if __name__ == "__main__":
    main()
