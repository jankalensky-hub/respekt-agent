#!/usr/bin/env python3
"""
Respekt EPUB Downloader pro GitHub Actions
Automaticky stáhne aktuální číslo Respektu a odešle na Kindle
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
            logger.info("Přihlašuji se na Respekt.cz...")
            
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
                # Zkusme vypsat HTML stránky pro debugging a screenshot
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
                    logger.info(f"Přihlášení potvrzeno - nalezen element: {element.text}")
                    return True
                except NoSuchElementException:
                    continue
            
            # Pokud jsme nebyli přesměrováni zpět na login, považujme to za úspěch
            if "prihlaseni" not in current_url:
                logger.info("Přihlášení úspěšné - nejsme na přihlašovací stránce")
                return True
            
            logger.warning("Nelze potvrdit úspěšné přihlášení, ale pokračuji...")
            return True
                
        except Exception as e:
            logger.error(f"Chyba při přihlašování: {e}")
            # Loguj více detailů pro debugging
            try:
                logger.error(f"Aktuální URL: {self.driver.current_url}")
                logger.error(f"Page title: {self.driver.title}")
            except:
                pass
            return False
    
    def find_current_issue(self):
        """Najde a stáhne aktuální číslo z archivu"""
        try:
            logger.info("Hledám aktuální vydání v archivu...")
            
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
                logger.error("Nenašel jsem žádné odkazy na vydání v archivu")
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
        """Stáhne EPUB z dané stránky vydání"""
        try:
            logger.info(f"Otevírám stránku vydání: {issue_url}")
            self.driver.get(issue_url)
            time.sleep(3)
            
            logger.info(f"Stránka vydání načtena, title: {self.driver.title}")
            
            # Hledej odkaz na EPUB - víme, že má formát /api/downloadEPub?issueId=...
            epub_selectors = [
                # API endpoint má prioritu
                "//a[contains(@href, '/api/downloadEPub')]",
                "//button[contains(@onclick, '/api/downloadEPub')]",
                # Tlačítko pro stažení
                "//button[contains(text(), 'Stáhnout epub')]",
                "//a[contains(text(), 'Stáhnout epub')]",
                "//button[contains(text(), 'EPUB')]",
                "//a[contains(text(), 'EPUB')]",
                # Obecné EPUB odkazy
                "//a[contains(@href, '.epub')]",
                "//a[contains(@href, 'epub')]",
                # CSS selektory
                "button[onclick*='downloadEPub']",
                "a[href*='/api/downloadEPub']",
                ".download-epub",
                ".epub-download"
            ]
            
            epub_element = None
            found_selector = None
            
            for selector in epub_selectors:
                try:
                    if selector.startswith("//"):
                        # XPath selektor
                        elements = self.driver.find_elements(By.XPATH, selector)
                    else:
                        # CSS selektor  
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    if elements:
                        epub_element = elements[0]
                        found_selector = selector
                        logger.info(f"EPUB element nalezen pomocí: {selector}")
                        logger.info(f"Text elementu: '{epub_element.text.strip()}'")
                        break
                        
                except Exception as e:
                    logger.debug(f"Selektor {selector} selhal: {e}")
                    continue
            
            if not epub_element:
                logger.error("Nenašel jsem odkaz na EPUB stažení")
                self.save_debug_info("issue_no_epub_link")
                
                # Zkusme najít všechny odkazy a vypsat je
                all_links = self.driver.find_elements(By.TAG_NAME, "a")
                logger.info(f"Všechny odkazy na stránce ({len(all_links)}):")
                for i, link in enumerate(all_links[:20]):  # Jen prvních 20
                    href = link.get_attribute('href')
                    text = link.text.strip()
                    if href:
                        logger.info(f"{i+1}. {text} -> {href}")
                
                return None
            
            # Získej URL pro stažení
            epub_url = epub_element.get_attribute('href')
            
            if not epub_url:
                # Možná je to tlačítko s onclick událostí
                onclick_attr = epub_element.get_attribute('onclick')
                if onclick_attr and 'downloadEPub' in onclick_attr:
                    # Extrahuj URL z onclick
                    import re
                    match = re.search(r'/api/downloadEPub\?issueId=([a-f0-9-]+)', onclick_attr)
                    if match:
                        epub_url = f"https://www.respekt.cz/api/downloadEPub?issueId={match.group(1)}"
                        logger.info(f"Extrahovana URL z onclick: {epub_url}")
                    
                if not epub_url:
                    # Zkus kliknout na tlačítko a zachytit network request
                    logger.info("Element nemá href, zkouším kliknout a zachytit download...")
                    
                    # Před kliknutím si poznač současnou URL
                    current_url = self.driver.current_url
                    
                    try:
                        epub_element.click()
                        time.sleep(3)
                        
                        # Zkontroluj, jestli se změnila URL nebo začal download
                        new_url = self.driver.current_url
                        if new_url != current_url and 'downloadEPub' in new_url:
                            epub_url = new_url
                            logger.info(f"Po kliknutí získána URL: {epub_url}")
                        else:
                            logger.error("Kliknutí na tlačítko nepřineslo download URL")
                            return None
                            
                    except Exception as click_error:
                        logger.error(f"Chyba při klikání na tlačítko: {click_error}")
                        return None
            
            logger.info(f"Nalezen EPUB URL: {epub_url}")
            
            # Stáhni EPUB pomocí session s cookies z prohlížeče
            cookies = self.driver.get_cookies()
            session = requests.Session()
            
            for cookie in cookies:
                session.cookies.set(cookie['name'], cookie['value'])
            
            # Nastav stejné headers jako prohlížeč
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': issue_url,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
            }
            
            logger.info(f"Stahování EPUB z: {epub_url}")
            response = session.get(epub_url, headers=headers)
            response.raise_for_status()
            
            # Zkontroluj, že jsme dostali EPUB soubor
            content_type = response.headers.get('Content-Type', '')
            content_length = len(response.content)
            
            logger.info(f"Content-Type: {content_type}")
            logger.info(f"Content-Length: {content_length} bytes")
            
            if content_length < 1000:  # EPUB by měl být větší
                logger.warning(f"Podezřele malý soubor ({content_length} bytes)")
                logger.info(f"Odpověď serveru: {response.text[:500]}")
            
            # Vytvoř název souboru
            today = datetime.now().strftime("%Y-%m-%d")
            filename = f"respekt_{today}.epub"
            
            with open(filename, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"EPUB úspěšně stažen: {filename} ({content_length} bytes)")
            return filename
            
        except Exception as e:
            logger.error(f"Chyba při stahování EPUB: {e}")
            self.save_debug_info("epub_download_error")
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
            logger.info("=== Spouštím Respekt EPUB Downloader v2.0 ===")
            logger.info("Verze: Přímé URL strategie s backup systémem")
            
            # Kontrola proměnných prostředí
            required_vars = ['RESPEKT_LOGIN', 'RESPEKT_PASSWORD', 'GMAIL_EMAIL', 'GMAIL_APP_PASSWORD', 'KINDLE_EMAIL']
            missing_vars = [var for var in required_vars if not os.getenv(var)]
            
            if missing_vars:
                logger.error(f"Chybí proměnné prostředí: {', '.join(missing_vars)}")
                return False
            
            # 1. Přihlášení
            if not self.login():
                return False
            
            # 2. Najdi aktuální vydání v archivu
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
