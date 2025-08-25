#!/usr/bin/env python3
"""
Respekt EPUB Downloader v3.0 - Nová verze s přímými URL
Automaticky stáhne aktuální číslo Respektu a odešle na Kindle
Build: 20250825
"""

import os
import time
import smtplib
import requests
import re
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
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
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-plugins')
        chrome_options.add_argument('--disable-images')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Dodatečné argumenty pro stabilitu
        chrome_options.add_argument('--disable-background-timer-throttling')
        chrome_options.add_argument('--disable-backgrounding-occluded-windows')
        chrome_options.add_argument('--disable-renderer-backgrounding')
        chrome_options.add_argument('--disable-features=TranslateUI')
        chrome_options.add_argument('--disable-ipc-flooding-protection')
        chrome_options.add_argument('--disable-client-side-phishing-detection')
        chrome_options.add_argument('--disable-default-apps')
        chrome_options.add_argument('--disable-hang-monitor')
        chrome_options.add_argument('--disable-popup-blocking')
        chrome_options.add_argument('--disable-prompt-on-repost')
        chrome_options.add_argument('--disable-sync')
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--metrics-recording-only')
        chrome_options.add_argument('--no-first-run')
        chrome_options.add_argument('--safebrowsing-disable-auto-update')
        chrome_options.add_argument('--enable-automation')
        chrome_options.add_argument('--password-store=basic')
        chrome_options.add_argument('--use-mock-keychain')
        
        try:
            self.driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=chrome_options
            )
            self.wait = WebDriverWait(self.driver, 30)
            logger.info("Browser inicializován úspěšně")
        except Exception as e:
            logger.error(f"Chyba při inicializaci browseru: {e}")
            raise
    
    def save_debug_info(self, name):
        """Uloží screenshot a HTML pro debugging"""
        try:
            # Uložit screenshot
            screenshot_path = f"debug_{name}.png"
            self.driver.save_screenshot(screenshot_path)
            logger.info(f"Screenshot uložen: {screenshot_path}")
            
            # Uložit HTML
            html_path = f"debug_{name}.html"
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            logger.info(f"HTML uloženo: {html_path}")
            
            # Vypsat část HTML do logu
            logger.info("HTML stránky (prvních 1500 znaků):")
            logger.info(self.driver.page_source[:1500])
            
        except Exception as e:
            logger.error(f"Chyba při ukládání debug info: {e}")
    
    def login(self):
        """Přihlášení na Respekt.cz"""
        try:
            logger.info("🔐 Přihlašuji se na Respekt.cz...")
            
            # Načti hlavní stránku nejdříve
            self.driver.get("https://www.respekt.cz")
            time.sleep(2)
            logger.info(f"Hlavní stránka načtena, title: {self.driver.title}")
            
            # Teď jdi na přihlášení  
            self.driver.get("https://www.respekt.cz/uzivatel/prihlaseni")
            time.sleep(3)
            logger.info(f"Přihlašovací stránka načtena, title: {self.driver.title}")
            
            # Zkus najít formulář různými způsoby
            email_field = None
            selectors_email = ["input[name='email']", "input[type='email']", "#email", ".email"]
            
            for selector in selectors_email:
                try:
                    email_field = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"Email pole nalezeno pomocí: {selector}")
                    break
                except TimeoutException:
                    logger.info(f"Email pole nenalezeno pomocí: {selector}")
                    continue
            
            if not email_field:
                logger.error("Nenašel jsem email pole")
                self.save_debug_info("login_page_no_email")
                return False
            
            # Hledej password pole
            password_field = None
            selectors_password = ["input[name='password']", "input[type='password']", "#password", ".password"]
            
            for selector in selectors_password:
                try:
                    password_field = self.driver.find_element(By.CSS_SELECTOR, selector)
                    logger.info(f"Password pole nalezeno pomocí: {selector}")
                    break
                except NoSuchElementException:
                    continue
            
            if not password_field:
                logger.error("Nenašel jsem password pole")
                return False
            
            # Vyplň přihlašovací údaje
            logger.info("Vyplňuji přihlašovací údaje...")
            email_field.clear()
            email_field.send_keys(RESPEKT_LOGIN)
            password_field.clear()
            password_field.send_keys(RESPEKT_PASSWORD)
            
            # Najdi a klikni submit button
            submit_selectors = [
                "button[type='submit']",
                "input[type='submit']", 
                "button:contains('Přihlásit')",
                ".submit-button",
                ".login-button"
            ]
            
            submit_button = None
            for selector in submit_selectors:
                try:
                    submit_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    logger.info(f"Submit button nalezen pomocí: {selector}")
                    break
                except NoSuchElementException:
                    continue
            
            if not submit_button:
                # Zkus najít pomocí textu
                try:
                    submit_button = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Přihlásit') or contains(text(), 'Login')]")
                    logger.info("Submit button nalezen pomocí XPath")
                except NoSuchElementException:
                    logger.error("Nenašel jsem submit button")
                    return False
            
            # Klikni na submit
            logger.info("Odesílám přihlašovací formulář...")
            submit_button.click()
            
            # Počkaj na přesměrování
            time.sleep(5)
            
            # Zkontroluj přihlášení
            current_url = self.driver.current_url
            logger.info(f"Aktuální URL po přihlášení: {current_url}")
            
            # Kontrola různých indikátorů úspěšného přihlášení
            login_indicators = [
                "//a[contains(@href, 'muj-ucet') or contains(text(), 'Můj účet')]",
                "//a[contains(@href, 'archiv') or contains(text(), 'Archiv')]",
                "//a[contains(@href, 'odhlaseni') or contains(text(), 'Odhlásit')]",
                "//div[contains(@class, 'user') or contains(@class, 'profile')]"
            ]
            
            for indicator in login_indicators:
                try:
                    element = self.driver.find_element(By.XPATH, indicator)
                    logger.info(f"✅ Přihlášení potvrzeno - nalezen element: {element.text}")
                    return True
                except NoSuchElementException:
                    continue
            
            # Pokud jsme nebyli přesměrováni zpět na login, považujme to za úspěch
            if "prihlaseni" not in current_url:
                logger.info("✅ Přihlášení úspěšné - nejsme na přihlašovací stránce")
                return True
            
            logger.warning("⚠️ Nelze potvrdit úspěšné přihlášení, ale pokračuji...")
            return True
                
        except Exception as e:
            logger.error(f"❌ Chyba při přihlašování: {e}")
            try:
                logger.error(f"Aktuální URL: {self.driver.current_url}")
                logger.error(f"Page title: {self.driver.title}")
            except:
                pass
            return False
    
    def find_current_issue(self):
        """🎯 Najde aktuální vydání pomocí přímých URL"""
        try:
            logger.info("🔍 Hledám aktuální vydání...")
            logger.info("🚀 Používám novou strategii přímých URL!")
            
            # Strategie 1: Zkusit přímo nejnovější vydání
            current_year = datetime.now().year
            logger.info(f"📅 Aktuální rok: {current_year}")
            
            # Začni od čísla 35 (víme, že existuje) a zkus okolní čísla
            issue_numbers = [35, 36, 34, 37, 33, 38, 32, 39, 31, 40]
            
            for issue_num in issue_numbers:
                test_url = f"https://www.respekt.cz/tydenik/{current_year}/{issue_num}"
                logger.info(f"🧪 Testuji vydání {issue_num}/2025: {test_url}")
                
                try:
                    self.driver.get(test_url)
                    time.sleep(3)
                    
                    title = self.driver.title
                    logger.info(f"📄 Title stránky: {title}")
                    
                    # Zkontroluj validitu stránky
                    if "404" not in title and "RESPEKT" in title and title != "RESPEKT":
                        logger.info(f"✅ Nalezeno funkční vydání {issue_num}/2025!")
                        logger.info(f"🎉 URL: {test_url}")
                        return test_url
                    else:
                        logger.info(f"❌ Vydání {issue_num}/2025 neexistuje nebo je prázdné")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Chyba při testování vydání {issue_num}: {e}")
                    continue
            
            logger.error("❌ Žádné přímé URL nevyhovovalo!")
            logger.info("🔄 Zkouším záložní metody...")
            
            # Strategie 2: Zkus archiv
            return self._find_issue_from_archive()
            
        except Exception as e:
            logger.error(f"💥 Chyba při hledání vydání: {e}")
            self.save_debug_info("find_issue_error")
            return None
    
    def _find_issue_from_archive(self):
        """Záložní metoda - hledání v archivu"""
        try:
            logger.info("📚 Zkouším archiv jako záložní možnost...")
            
            current_year = datetime.now().year
            archive_url = f"https://www.respekt.cz/archiv/{current_year}"
            self.driver.get(archive_url)
            time.sleep(5)
            
            logger.info(f"Archive načten: {self.driver.title}")
            
            # Hledej odkazy na vydání
            selectors = [
                f"//a[contains(@href, '/tydenik/{current_year}/')]",
                "//a[contains(@href, '/tydenik/')]"
            ]
            
            for selector in selectors:
                try:
                    issues = self.driver.find_elements(By.XPATH, selector)
                    if issues:
                        issue_url = issues[0].get_attribute('href')
                        logger.info(f"✅ Nalezeno v archivu: {issue_url}")
                        return issue_url
                except Exception as e:
                    logger.debug(f"Selektor {selector} selhal: {e}")
                    continue
            
            logger.error("❌ Ani archiv nefunguje")
            return None
            
        except Exception as e:
            logger.error(f"💥 Chyba v archivu: {e}")
            return None
    
    def download_epub(self, issue_url):
        """📥 Stáhne EPUB z dané stránky vydání"""
        try:
            logger.info(f"📖 Otevírám stránku vydání: {issue_url}")
            self.driver.get(issue_url)
            time.sleep(3)
            
            logger.info(f"📄 Stránka vydání načtena, title: {self.driver.title}")
            
            # Hledej EPUB download - víme přesný formát API
            epub_selectors = [
                "//a[contains(@href, '/api/downloadEPub')]",
                "//button[contains(@onclick, '/api/downloadEPub')]",
                "//button[contains(text(), 'Stáhnout epub')]",
                "//a[contains(text(), 'Stáhnout epub')]",
                "//button[contains(text(), 'EPUB')]",
                "//a[contains(text(), 'EPUB')]",
                "button[onclick*='downloadEPub']",
                "a[href*='/api/downloadEPub']"
            ]
            
            epub_element = None
            found_selector = None
            
            for selector in epub_selectors:
                try:
                    if selector.startswith("//"):
                        elements = self.driver.find_elements(By.XPATH, selector)
                    else:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    if elements:
                        epub_element = elements[0]
                        found_selector = selector
                        logger.info(f"📥 EPUB element nalezen: {selector}")
                        logger.info(f"📝 Text elementu: '{epub_element.text.strip()}'")
                        break
                        
                except Exception as e:
                    logger.debug(f"Selektor {selector} selhal: {e}")
                    continue
            
            if not epub_element:
                logger.error("❌ Nenašel jsem EPUB odkaz!")
                self.save_debug_info("issue_no_epub_link")
                return None
            
            # Získej URL pro stažení
            epub_url = epub_element.get_attribute('href')
            
            if not epub_url:
                # Zkus extrahovat z onclick
                onclick_attr = epub_element.get_attribute('onclick')
                if onclick_attr and 'downloadEPub' in onclick_attr:
                    match = re.search(r'/api/downloadEPub\?issueId=([a-f0-9-]+)', onclick_attr)
                    if match:
                        epub_url = f"https://www.respekt.cz/api/downloadEPub?issueId={match.group(1)}"
                        logger.info(f"📄 URL extrahovana z onclick: {epub_url}")
                
                if not epub_url:
                    logger.error("❌ Nelze získat EPUB URL")
                    return None
            
            logger.info(f"🎯 EPUB URL nalezena: {epub_url}")
            
            # Stáhni pomocí autentizované session
            cookies = self.driver.get_cookies()
            session = requests.Session()
            
            for cookie in cookies:
                session.cookies.set(cookie['name'], cookie['value'])
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': issue_url,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
            }
            
            logger.info(f"⬇️ Stahování EPUB...")
            response = session.get(epub_url, headers=headers)
            response.raise_for_status()
            
            content_length = len(response.content)
            logger.info(f"📊 Staženo {content_length} bytes")
            
            if content_length < 1000:
                logger.warning(f"⚠️ Podezřele malý soubor ({content_length} bytes)")
                logger.info(f"Response: {response.text[:500]}")
            
            # Vytvoř název souboru
            today = datetime.now().strftime("%Y-%m-%d")
            filename = f"respekt_{today}.epub"
            
            with open(filename, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"✅ EPUB úspěšně stažen: {filename} ({content_length} bytes)")
            return filename
            
        except Exception as e:
            logger.error(f"💥 Chyba při stahování EPUB: {e}")
            self.save_debug_info("epub_download_error")
            return None
    
    def send_to_kindle(self, epub_file):
        """📧 Odešle EPUB na Kindle"""
        try:
            logger.info(f"📤 Odesílám {epub_file} na Kindle ({KINDLE_EMAIL})...")
            
            msg = MIMEMultipart()
            msg['From'] = GMAIL_EMAIL
            msg['To'] = KINDLE_EMAIL
            msg['Subject'] = f"Respekt - {datetime.now().strftime('%d.%m.%Y')}"
            
            with open(epub_file, "rb") as attachment:
                part = MIMEBase('application', 'epub+zip')
                part.set_payload(attachment.read())
            
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{epub_file}"')
            msg.attach(part)
            
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
                server.send_message(msg)
            
            logger.info("✅ Email úspěšně odeslán na Kindle!")
            return True
            
        except Exception as e:
            logger.error(f"💥 Chyba při odesílání emailu: {e}")
            return False
    
    def run(self):
        """🚀 Hlavní metoda - spustí celý proces"""
        try:
            logger.info("🎬 === Spouštím Respekt EPUB Downloader v3.0 - NOVÁ VERZE ===")
            logger.info("📦 Verze: Přímé URL strategie s backup systémem (build 20250825)")
            logger.info("🚀 Nový algoritmus pro hledání vydání aktivní!")
            
            # Kontrola proměnných prostředí
            required_vars = ['RESPEKT_LOGIN', 'RESPEKT_PASSWORD', 'GMAIL_EMAIL', 'GMAIL_APP_PASSWORD', 'KINDLE_EMAIL']
            missing_vars = [var for var in required_vars if not os.getenv(var)]
            
            if missing_vars:
                logger.error(f"❌ Chybí proměnné prostředí: {', '.join(missing_vars)}")
                return False
            
            logger.info("✅ Všechny proměnné prostředí jsou nastavené")
            
            # 1. Přihlášení
            if not self.login():
                return False
            
            # 2. Najdi aktuální vydání
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
                logger.info("🎉 === Proces úspěšně dokončen! ===")
                try:
                    os.remove(epub_file)
                    logger.info(f"🗑️ Místní soubor {epub_file} smazán")
                except:
                    pass
            
            return success
            
        except Exception as e:
            logger.error(f"💥 Neočekávaná chyba: {e}")
            return False
        
        finally:
            if self.driver:
                self.driver.quit()

def main():
    """Hlavní funkce"""
    logger.info("🌟 Respekt EPUB Downloader v3.0 - Starting...")
    
    downloader = RespektDownloader()
    success = downloader.run()
    
    if not success:
        logger.error("❌ Proces selhal!")
        exit(1)
    
    logger.info("✅ Hotovo!")

if __name__ == "__main__":
    main()
