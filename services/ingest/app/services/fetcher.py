"""
Fetcher service for retrieving invoices from various sources
"""
import asyncio
import imaplib
import email
import email.policy
import io
import time
from typing import List, Dict, Any, Optional, Tuple, AsyncGenerator
from dataclasses import dataclass
from pathlib import Path

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..core.config import settings
from ..core.logging import get_logger, log_function_call, log_function_result, log_error
from ..models.invoice import InvoiceSource


logger = get_logger(__name__)


@dataclass
class FetchedDocument:
    """Represents a fetched document"""
    source: InvoiceSource
    source_identifier: str
    filename: str
    content: bytes
    content_type: str
    metadata: Dict[str, Any]
    size: int


class EmailFetcher:
    """IMAP email fetcher for downloading PDF/JSON attachments"""
    
    def __init__(self):
        self.imap_server = None
        
    async def connect(self) -> None:
        """Connect to IMAP server"""
        log_function_call("EmailFetcher.connect")
        start_time = time.time()
        
        try:
            if settings.IMAP_USE_SSL:
                self.imap_server = imaplib.IMAP4_SSL(settings.IMAP_URL, settings.IMAP_PORT)
            else:
                self.imap_server = imaplib.IMAP4(settings.IMAP_URL, settings.IMAP_PORT)
            
            if settings.IMAP_USERNAME and settings.IMAP_PASSWORD:
                self.imap_server.login(settings.IMAP_USERNAME, settings.IMAP_PASSWORD)
                logger.info(f"Connected to IMAP server {settings.IMAP_URL}")
            else:
                raise ValueError("IMAP credentials not configured")
                
        except Exception as e:
            log_error(e, {"imap_url": settings.IMAP_URL})
            raise
        finally:
            log_function_result("EmailFetcher.connect", None, time.time() - start_time)
    
    async def disconnect(self) -> None:
        """Disconnect from IMAP server"""
        if self.imap_server:
            try:
                self.imap_server.logout()
            except Exception as e:
                log_error(e, {"operation": "imap_logout"})
            finally:
                self.imap_server = None
    
    async def fetch_attachments(self, 
                              since_date: Optional[str] = None,
                              subject_filter: Optional[str] = None) -> AsyncGenerator[FetchedDocument, None]:
        """Fetch PDF/JSON attachments from mailbox"""
        log_function_call("EmailFetcher.fetch_attachments", 
                         since_date=since_date, subject_filter=subject_filter)
        
        if not self.imap_server:
            await self.connect()
        
        try:
            # Select mailbox
            self.imap_server.select(settings.IMAP_MAILBOX)
            
            # Build search criteria
            search_criteria = ["ALL"]
            if since_date:
                search_criteria = ["SINCE", since_date]
            if subject_filter:
                search_criteria.extend(["SUBJECT", subject_filter])
            
            # Search for emails
            _, message_ids = self.imap_server.search(None, *search_criteria)
            
            for msg_id in message_ids[0].split():
                try:
                    # Fetch email
                    _, msg_data = self.imap_server.fetch(msg_id, "(RFC822)")
                    email_msg = email.message_from_bytes(msg_data[0][1], policy=email.policy.default)
                    
                    # Process attachments
                    async for document in self._process_email_attachments(email_msg, msg_id.decode()):
                        yield document
                        
                except Exception as e:
                    log_error(e, {"message_id": msg_id.decode()})
                    continue
                    
        except Exception as e:
            log_error(e, {"operation": "fetch_attachments"})
            raise
    
    async def _process_email_attachments(self, email_msg, msg_id: str) -> AsyncGenerator[FetchedDocument, None]:
        """Process attachments from an email message"""
        for part in email_msg.walk():
            if part.get_content_disposition() == "attachment":
                filename = part.get_filename()
                if not filename:
                    continue
                
                # Check if file extension is allowed
                file_extension = Path(filename).suffix.lower()
                if file_extension not in settings.ALLOWED_EXTENSIONS:
                    logger.debug(f"Skipping attachment {filename} - unsupported extension")
                    continue
                
                content = part.get_payload(decode=True)
                if not content:
                    continue
                
                # Check file size
                if len(content) > settings.MAX_FILE_SIZE:
                    logger.warning(f"Skipping attachment {filename} - too large ({len(content)} bytes)")
                    continue
                
                metadata = {
                    "email_subject": email_msg.get("Subject", ""),
                    "email_from": email_msg.get("From", ""),
                    "email_date": email_msg.get("Date", ""),
                    "message_id": msg_id,
                }
                
                yield FetchedDocument(
                    source=InvoiceSource.EMAIL,
                    source_identifier=f"email_{msg_id}_{filename}",
                    filename=filename,
                    content=content,
                    content_type=part.get_content_type() or "application/octet-stream",
                    metadata=metadata,
                    size=len(content)
                )


class ScrapyInvoiceSpider(scrapy.Spider):
    """Scrapy spider for scraping invoices from web pages"""
    name = 'invoice_spider'
    
    def __init__(self, urls: List[str], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = urls
        self.scraped_documents = []
    
    def parse(self, response):
        """Parse response and extract invoice documents"""
        # Look for common invoice file patterns
        invoice_links = response.css('a[href$=".pdf"], a[href$=".json"]').getall()
        
        for link in invoice_links:
            file_url = response.urljoin(link.get('href'))
            yield scrapy.Request(file_url, callback=self.parse_file)
    
    def parse_file(self, response):
        """Download and process invoice files"""
        filename = response.url.split('/')[-1]
        
        if len(response.body) > settings.MAX_FILE_SIZE:
            self.logger.warning(f"File {filename} too large, skipping")
            return
        
        document = FetchedDocument(
            source=InvoiceSource.HTTP,
            source_identifier=f"http_{response.url}",
            filename=filename,
            content=response.body,
            content_type=response.headers.get('Content-Type', b'').decode(),
            metadata={
                "url": response.url,
                "scraped_at": time.time(),
            },
            size=len(response.body)
        )
        
        self.scraped_documents.append(document)


class HTTPFetcher:
    """HTTP fetcher using Scrapy and Selenium for JS-heavy pages"""
    
    def __init__(self):
        self.driver = None
    
    @retry(
        stop=stop_after_attempt(settings.MAX_RETRIES),
        wait=wait_exponential(multiplier=settings.RETRY_DELAY, max=60),
        retry=retry_if_exception_type((requests.exceptions.HTTPError, 
                                     requests.exceptions.ConnectionError,
                                     requests.exceptions.Timeout))
    )
    async def fetch_with_scrapy(self, urls: List[str]) -> List[FetchedDocument]:
        """Fetch documents using Scrapy"""
        log_function_call("HTTPFetcher.fetch_with_scrapy", urls=urls)
        start_time = time.time()
        
        try:
            # Configure Scrapy settings
            scrapy_settings = get_project_settings()
            scrapy_settings.update({
                'USER_AGENT': 'InvoiceFlow Bot 1.0',
                'ROBOTSTXT_OBEY': True,
                'CONCURRENT_REQUESTS': 4,
                'DOWNLOAD_TIMEOUT': 30,
                'RETRY_TIMES': settings.MAX_RETRIES,
            })
            
            # Create and run spider
            spider = ScrapyInvoiceSpider(urls)
            process = CrawlerProcess(scrapy_settings)
            
            # Run spider in executor to avoid blocking
            def run_spider():
                process.crawl(spider)
                process.start(stop_after_crawl=True)
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, run_spider)
            
            return spider.scraped_documents
            
        except Exception as e:
            log_error(e, {"urls": urls})
            raise
        finally:
            log_function_result("HTTPFetcher.fetch_with_scrapy", 
                              len(spider.scraped_documents) if 'spider' in locals() else 0,
                              time.time() - start_time)
    
    async def setup_selenium_driver(self) -> None:
        """Setup Selenium WebDriver"""
        if self.driver:
            return
        
        try:
            chrome_options = ChromeOptions()
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            
            if settings.SELENIUM_HEADLESS:
                chrome_options.add_argument("--headless")
            
            # Auto-download ChromeDriver
            driver_path = ChromeDriverManager().install()
            
            self.driver = webdriver.Chrome(
                executable_path=driver_path,
                options=chrome_options
            )
            
            self.driver.implicitly_wait(settings.SELENIUM_IMPLICIT_WAIT)
            logger.info("Selenium WebDriver initialized")
            
        except Exception as e:
            log_error(e, {"operation": "selenium_setup"})
            raise
    
    @retry(
        stop=stop_after_attempt(settings.MAX_RETRIES),
        wait=wait_exponential(multiplier=settings.RETRY_DELAY, max=60),
        retry=retry_if_exception_type((WebDriverException, TimeoutException))
    )
    async def fetch_with_selenium(self, urls: List[str]) -> List[FetchedDocument]:
        """Fetch documents using Selenium for JS-heavy pages"""
        log_function_call("HTTPFetcher.fetch_with_selenium", urls=urls)
        start_time = time.time()
        
        await self.setup_selenium_driver()
        documents = []
        
        try:
            for url in urls:
                try:
                    self.driver.get(url)
                    
                    # Wait for page to load
                    WebDriverWait(self.driver, settings.SELENIUM_TIMEOUT).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    
                    # Look for download links
                    download_links = self.driver.find_elements(
                        By.CSS_SELECTOR, 
                        'a[href$=".pdf"], a[href$=".json"], button[data-download]'
                    )
                    
                    for link in download_links:
                        try:
                            # Get file URL
                            file_url = link.get_attribute('href') or link.get_attribute('data-download')
                            if not file_url:
                                continue
                            
                            # Download file using requests
                            response = requests.get(file_url, timeout=30)
                            response.raise_for_status()
                            
                            if len(response.content) > settings.MAX_FILE_SIZE:
                                logger.warning(f"File at {file_url} too large, skipping")
                                continue
                            
                            filename = file_url.split('/')[-1] or f"document_{int(time.time())}.pdf"
                            
                            document = FetchedDocument(
                                source=InvoiceSource.HTTP,
                                source_identifier=f"selenium_{file_url}",
                                filename=filename,
                                content=response.content,
                                content_type=response.headers.get('Content-Type', 'application/octet-stream'),
                                metadata={
                                    "url": file_url,
                                    "page_url": url,
                                    "scraped_at": time.time(),
                                },
                                size=len(response.content)
                            )
                            
                            documents.append(document)
                            
                        except Exception as e:
                            log_error(e, {"link_url": file_url})
                            continue
                            
                except Exception as e:
                    log_error(e, {"url": url})
                    continue
            
            return documents
            
        finally:
            log_function_result("HTTPFetcher.fetch_with_selenium", 
                              len(documents), time.time() - start_time)
    
    async def cleanup(self) -> None:
        """Cleanup Selenium driver"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                log_error(e, {"operation": "selenium_cleanup"})
            finally:
                self.driver = None


class UnifiedFetcher:
    """Unified fetcher that combines email and HTTP fetching capabilities"""
    
    def __init__(self):
        self.email_fetcher = EmailFetcher()
        self.http_fetcher = HTTPFetcher()
    
    async def fetch_from_email(self, **kwargs) -> AsyncGenerator[FetchedDocument, None]:
        """Fetch documents from email"""
        async for document in self.email_fetcher.fetch_attachments(**kwargs):
            yield document
    
    async def fetch_from_http(self, urls: List[str], use_selenium: bool = False) -> List[FetchedDocument]:
        """Fetch documents from HTTP sources"""
        if use_selenium:
            return await self.http_fetcher.fetch_with_selenium(urls)
        else:
            # Try Scrapy first, fallback to Selenium if needed
            try:
                documents = await self.http_fetcher.fetch_with_scrapy(urls)
                if not documents:
                    logger.info("Scrapy returned no results, falling back to Selenium")
                    documents = await self.http_fetcher.fetch_with_selenium(urls)
                return documents
            except Exception as e:
                log_error(e, {"fallback": "selenium"})
                return await self.http_fetcher.fetch_with_selenium(urls)
    
    async def cleanup(self) -> None:
        """Cleanup all resources"""
        await self.email_fetcher.disconnect()
        await self.http_fetcher.cleanup() 