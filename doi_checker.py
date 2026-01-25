#!/usr/bin/env python3
"""
DOI and Reference Checker
Extracts references from research papers (PDF) and validates DOI/URLs
"""

import re
import sys
import json
import time
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse
import PyPDF2
import requests
from bs4 import BeautifulSoup
from fuzzywuzzy import fuzz


class Reference:
    """Represents a single reference from a paper"""

    def __init__(self, raw_text: str):
        self.raw_text = raw_text
        self.authors: List[str] = []
        self.title: str = ""
        self.doi: Optional[str] = None
        self.urls: List[str] = []
        self.year: Optional[str] = None
        self.is_accessible: bool = False
        self.url_check_results: Dict[str, Dict] = {}
        self.search_results: Optional[Dict] = None

    def __repr__(self):
        return f"Reference(authors={self.authors[:2]}..., title={self.title[:50]}...)"


class PDFReferenceExtractor:
    """Extracts references from PDF files"""

    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)
        self.text = ""
        self.references: List[Reference] = []

    def extract_text(self) -> str:
        """Extract text from PDF"""
        print(f"Extracting text from {self.pdf_path}...")
        try:
            with open(self.pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                self.text = text
                return text
        except Exception as e:
            print(f"Error extracting text from PDF: {e}")
            return ""

    def find_references_section(self) -> str:
        """Find and extract the references section from the text"""
        print("Looking for references section...")

        # Common patterns for references section
        patterns = [
            r'(?:REFERENCES|References|BIBLIOGRAPHY|Bibliography)\s*\n(.*?)(?:\n\s*\n|\Z)',
            r'(?:REFERENCES|References|BIBLIOGRAPHY|Bibliography)\s*(.*?)(?:\n\s*APPENDIX|\n\s*Appendix|\Z)',
        ]

        for pattern in patterns:
            match = re.search(pattern, self.text, re.DOTALL | re.IGNORECASE)
            if match:
                refs_text = match.group(1)
                print(f"Found references section ({len(refs_text)} characters)")
                return refs_text

        # If no clear section, try to find references at the end
        print("No clear references section found, trying alternative methods...")
        return ""

    def parse_references(self, refs_text: str) -> List[Reference]:
        """Parse individual references from the references section"""
        print("Parsing individual references...")

        # Split by common reference numbering patterns
        # Patterns: [1], 1., (1), [1], etc.
        ref_patterns = [
            r'\n\s*\[(\d+)\]\s*',  # [1]
            r'\n\s*(\d+)\.\s+',     # 1.
            r'\n\s*\((\d+)\)\s*',   # (1)
        ]

        references = []
        split_refs = []

        for pattern in ref_patterns:
            if re.search(pattern, refs_text):
                parts = re.split(pattern, refs_text)

                # Handle first part if not empty (contains first reference)
                if parts[0].strip() != '':
                    # First part contains the first reference, extract it
                    first_ref = parts[0].strip()
                    if first_ref:
                        split_refs.append(first_ref)
                    # Remove first part so the rest are properly paired
                    parts = parts[1:]
                else:
                    # Remove first empty part
                    parts = parts[1:]

                # Group number and text (number at even index, text at odd index)
                for i in range(0, len(parts), 2):
                    if i+1 < len(parts):
                        ref_text = parts[i+1].strip()
                        if ref_text:
                            split_refs.append(ref_text)

                if split_refs:
                    break

        # If no numbered references found, try splitting by newlines
        if not split_refs:
            print("No numbered references found, trying line-based splitting...")
            lines = refs_text.split('\n')
            current_ref = ""
            for line in lines:
                line = line.strip()
                if not line:
                    if current_ref:
                        split_refs.append(current_ref)
                        current_ref = ""
                else:
                    # Check if this looks like a new reference (starts with capital or author name)
                    if current_ref and (re.match(r'^[A-Z][a-z]+,\s*[A-Z]', line) or
                                       re.match(r'^[A-Z][a-z]+\s+[A-Z]', line)):
                        split_refs.append(current_ref)
                        current_ref = line
                    else:
                        current_ref += " " + line if current_ref else line

            if current_ref:
                split_refs.append(current_ref)

        print(f"Found {len(split_refs)} potential references")

        # Create Reference objects and parse each one
        for ref_text in split_refs:
            if len(ref_text) > 20:  # Filter out too-short entries
                ref = Reference(ref_text)
                self._parse_reference_details(ref)
                references.append(ref)

        self.references = references
        return references

    def _parse_reference_details(self, ref: Reference):
        """Parse details from a reference text"""
        text = ref.raw_text

        # Extract DOI
        doi_pattern = r'(?:doi|DOI)[\s:]*10\.\d{4,}(?:\.\d+)*/[^\s,;]+'
        doi_match = re.search(doi_pattern, text, re.IGNORECASE)
        if doi_match:
            ref.doi = doi_match.group(0).split(':', 1)[-1].strip().rstrip('.,;')
            ref.urls.append(f"https://doi.org/{ref.doi}")

        # Extract URLs
        url_pattern = r'https?://[^\s,\]\)]+(?:[^\s\.,\]\)])'
        urls = re.findall(url_pattern, text)
        for url in urls:
            url = url.rstrip('.,;)')
            if url not in ref.urls:
                ref.urls.append(url)

        # Extract year
        year_pattern = r'\b(19|20)\d{2}\b'
        year_matches = re.findall(year_pattern, text)
        if year_matches:
            ref.year = year_matches[0]

        # Extract authors and title (this is complex and heuristic-based)
        self._extract_authors_and_title(ref)

    def _extract_authors_and_title(self, ref: Reference):
        """Extract authors and title from reference text"""
        text = ref.raw_text

        # Remove URLs and DOI from text for cleaner parsing
        clean_text = re.sub(r'https?://[^\s]+', '', text)
        clean_text = re.sub(r'(?:doi|DOI)[\s:]*[10]\.\d{4,}(?:\.\d+)*\/[^\s]+', '', clean_text)

        # Common patterns for authors (Last, F. M., or Last F.M., or Last F M)
        # Authors usually come first, before the title

        # Try to identify title (usually in quotes or after authors)
        title_patterns = [
            r'"([^"]+)"',  # "Title in quotes"
            r"'([^']+)'",  # 'Title in quotes'
            r'``([^`]+)\'\'',  # ``Title''
        ]

        for pattern in title_patterns:
            match = re.search(pattern, clean_text)
            if match:
                ref.title = match.group(1).strip()
                # Remove title from text to make author extraction easier
                clean_text = clean_text.replace(match.group(0), '', 1)
                break

        # If no quoted title, try to extract it heuristically
        if not ref.title:
            # Title often comes after authors and before year/journal
            # Split by common delimiters
            parts = re.split(r'[,\.]', clean_text)
            # Look for a longer part that might be the title
            for i, part in enumerate(parts):
                part = part.strip()
                if len(part) > 30 and not re.match(r'^[A-Z]\s*\.\s*[A-Z]', part):
                    # This might be the title
                    ref.title = part
                    break

        # Extract authors (names before the title or at the beginning)
        # This is simplified - real implementation would need more sophisticated parsing
        author_text = clean_text
        if ref.title:
            title_pos = clean_text.find(ref.title)
            if title_pos > 0:
                author_text = clean_text[:title_pos]

        # Look for author patterns
        # Pattern: Last, F. M., or Last, F.M., or Last F. M.
        author_patterns = [
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),\s*([A-Z]\.(?:\s*[A-Z]\.)*)',  # Last, F. M.
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+([A-Z]\.(?:\s*[A-Z]\.)*)',   # Last F. M.
        ]

        authors = []
        for pattern in author_patterns:
            matches = re.findall(pattern, author_text)
            for match in matches:
                last_name, initials = match
                author_name = f"{last_name}, {initials}"
                if author_name not in authors:
                    authors.append(author_name)

        # Also try to find "and" or "&" separated names
        and_split = re.split(r'\s+and\s+|\s*&\s*', author_text)
        for part in and_split:
            part = part.strip().rstrip(',.')
            if part and len(part) > 3 and part not in authors:
                # Check if it looks like a name
                if re.match(r'^[A-Z][a-z]+', part):
                    authors.append(part)

        ref.authors = authors[:10]  # Limit to first 10 authors


class URLValidator:
    """Validates URLs and checks content matching"""

    def __init__(self, timeout: int = 10, delay: float = 1.0, enable_search: bool = False):
        self.timeout = timeout
        self.delay = delay  # Delay between requests to be respectful
        self.enable_search = enable_search
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def check_reference(self, ref: Reference) -> Dict:
        """Check all URLs for a reference"""
        results = {
            'accessible_urls': [],
            'inaccessible_urls': [],
            'match_results': []
        }

        for url in ref.urls:
            print(f"  Checking URL: {url}")
            time.sleep(self.delay)  # Be respectful to servers

            try:
                # Use tuple timeout: (connect timeout, read timeout)
                # This prevents hanging on slow servers that accept connection but don't respond
                response = self.session.get(url, timeout=(self.timeout, self.timeout * 2), allow_redirects=True)

                # Accept any 2xx status code as successful (includes redirects)
                if 200 <= response.status_code < 300:
                    results['accessible_urls'].append(url)
                    ref.is_accessible = True

                    # Log if URL was redirected
                    final_url = response.url
                    if final_url != url:
                        print(f"    [OK] Redirected to: {final_url[:60]}...")

                    # Check content matching
                    match_result = self._check_content_match(response, ref)
                    match_result['url'] = url
                    match_result['final_url'] = final_url
                    results['match_results'].append(match_result)

                    print(f"    [OK] Accessible (status: {response.status_code})")
                    if match_result['title_match'] > 60:
                        print(f"    [OK] Title match: {match_result['title_match']}%")
                    if match_result['authors_found'] > 0:
                        print(f"    [OK] Found {match_result['authors_found']} authors")
                else:
                    results['inaccessible_urls'].append({
                        'url': url,
                        'status_code': response.status_code,
                        'reason': f"HTTP {response.status_code}"
                    })
                    print(f"    [X] Not accessible (status: {response.status_code})")

            except requests.exceptions.Timeout:
                results['inaccessible_urls'].append({
                    'url': url,
                    'reason': 'Timeout'
                })
                print(f"    [X] Timeout")
            except requests.exceptions.RequestException as e:
                results['inaccessible_urls'].append({
                    'url': url,
                    'reason': str(e)
                })
                print(f"    [X] Error: {str(e)[:50]}")

        # If no URLs found and search is enabled, search online
        if not ref.urls and self.enable_search:
            search_results = self.search_reference_online(ref)
            ref.search_results = search_results

        ref.url_check_results = results
        return results

    def _check_content_match(self, response: requests.Response, ref: Reference) -> Dict:
        """Check if page content matches reference details"""
        result = {
            'title_match': 0,
            'authors_found': 0,
            'author_matches': []
        }

        try:
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract text from page
            page_text = soup.get_text()

            # Also check meta tags
            meta_title = soup.find('meta', {'name': 'citation_title'})
            meta_authors = soup.find_all('meta', {'name': 'citation_author'})

            # Check title match
            if ref.title:
                # Check in meta tag first
                if meta_title and meta_title.get('content'):
                    meta_title_text = meta_title['content']
                    result['title_match'] = fuzz.partial_ratio(
                        ref.title.lower(),
                        meta_title_text.lower()
                    )
                else:
                    # Check in page text
                    result['title_match'] = fuzz.partial_ratio(
                        ref.title.lower(),
                        page_text.lower()
                    )

            # Check authors
            if ref.authors:
                # Check meta tags first
                if meta_authors:
                    for meta_author in meta_authors:
                        author_name = meta_author.get('content', '')
                        for ref_author in ref.authors:
                            if self._author_matches(ref_author, author_name):
                                result['authors_found'] += 1
                                result['author_matches'].append({
                                    'reference': ref_author,
                                    'found': author_name
                                })
                                break
                else:
                    # Check in page text
                    for author in ref.authors:
                        # Extract last name
                        last_name = author.split(',')[0].strip() if ',' in author else author.split()[0]
                        if last_name.lower() in page_text.lower():
                            result['authors_found'] += 1
                            result['author_matches'].append({
                                'reference': author,
                                'found': last_name
                            })

        except Exception as e:
            print(f"    Warning: Error checking content match: {e}")

        return result

    def _author_matches(self, ref_author: str, found_author: str) -> bool:
        """Check if two author names match"""
        # Simple fuzzy matching
        return fuzz.ratio(ref_author.lower(), found_author.lower()) > 80

    def search_reference_online(self, ref: Reference) -> Dict:
        """Search for a reference online when no URL is available"""
        if not self.enable_search:
            return {'search_performed': False}

        print(f"  Searching online for reference...")

        # Build search query from reference information
        query_parts = []
        if ref.title:
            query_parts.append(ref.title[:100])  # Limit title length
        if ref.authors:
            # Add first author
            query_parts.append(ref.authors[0])
        if ref.year:
            query_parts.append(ref.year)

        if not query_parts:
            print("    [X] Insufficient information to search")
            return {'search_performed': False, 'reason': 'insufficient_info'}

        query = ' '.join(query_parts)

        try:
            time.sleep(self.delay)
            search_results = self._perform_search(query)

            if not search_results:
                print("    [X] No search results found")
                return {
                    'search_performed': True,
                    'query': query,
                    'results': [],
                    'best_match': None
                }

            # Check each result for matching content
            match_scores = []
            for i, result in enumerate(search_results[:5], 1):  # First 5 results
                print(f"    Checking result {i}/{min(5, len(search_results))}: {result['url'][:50]}...")
                score = self._check_search_result_match(result, ref)
                match_scores.append({
                    'rank': i,
                    'url': result['url'],
                    'title': result.get('title', ''),
                    'snippet': result.get('snippet', ''),
                    'match_score': score
                })
                time.sleep(self.delay)

            # Find best match
            best_match = max(match_scores, key=lambda x: x['match_score']) if match_scores else None

            if best_match and best_match['match_score'] > 50:
                print(f"    [OK] Best match: {best_match['match_score']}% (result #{best_match['rank']})")
            else:
                print(f"    [!] Low confidence matches")

            return {
                'search_performed': True,
                'query': query,
                'results': match_scores,
                'best_match': best_match
            }

        except Exception as e:
            print(f"    [X] Search error: {str(e)[:50]}")
            return {
                'search_performed': True,
                'error': str(e)
            }

    def _perform_search(self, query: str) -> List[Dict]:
        """Perform web search using DuckDuckGo HTML"""
        try:
            # Use DuckDuckGo HTML search (no API key needed)
            search_url = "https://html.duckduckgo.com/html/"
            params = {'q': query}

            response = self.session.post(search_url, data=params, timeout=self.timeout)

            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.content, 'html.parser')
            results = []

            # Parse DuckDuckGo results
            for result_div in soup.find_all('div', class_='result')[:5]:
                try:
                    title_elem = result_div.find('a', class_='result__a')
                    snippet_elem = result_div.find('a', class_='result__snippet')

                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        url = title_elem.get('href', '')
                        snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''

                        results.append({
                            'title': title,
                            'url': url,
                            'snippet': snippet
                        })
                except Exception:
                    continue

            return results

        except Exception as e:
            print(f"    Search failed: {e}")
            return []

    def _check_search_result_match(self, search_result: Dict, ref: Reference) -> int:
        """Check how well a search result matches the reference"""
        scores = []

        # Check title match
        if ref.title and search_result.get('title'):
            title_score = fuzz.partial_ratio(
                ref.title.lower(),
                search_result['title'].lower()
            )
            scores.append(title_score * 2)  # Weight title heavily

        # Check snippet match with title
        if ref.title and search_result.get('snippet'):
            snippet_title_score = fuzz.partial_ratio(
                ref.title.lower(),
                search_result['snippet'].lower()
            )
            scores.append(snippet_title_score)

        # Check author match in snippet
        if ref.authors and search_result.get('snippet'):
            snippet_text = search_result['snippet'].lower()
            author_found = False
            for author in ref.authors[:3]:  # Check first 3 authors
                # Extract last name
                last_name = author.split(',')[0].strip() if ',' in author else author.split()[0]
                if last_name.lower() in snippet_text:
                    author_found = True
                    break
            if author_found:
                scores.append(70)  # Boost score if author found

        # Check year match
        if ref.year and search_result.get('snippet'):
            if ref.year in search_result['snippet']:
                scores.append(50)

        # Return average score
        return int(sum(scores) / len(scores)) if scores else 0


class ReportGenerator:
    """Generates reports from validation results"""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_json_report(self, references: List[Reference], filename: str = "references.json"):
        """Generate JSON report"""
        output_path = self.output_dir / filename

        data = []
        for i, ref in enumerate(references, 1):
            ref_data = {
                'number': i,
                'raw_text': ref.raw_text,
                'authors': ref.authors,
                'title': ref.title,
                'year': ref.year,
                'doi': ref.doi,
                'urls': ref.urls,
                'is_accessible': ref.is_accessible,
                'validation_results': ref.url_check_results,
                'search_results': ref.search_results
            }
            data.append(ref_data)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"\nJSON report saved to: {output_path}")
        return output_path

    def generate_text_report(self, references: List[Reference], filename: str = "references.txt"):
        """Generate human-readable text report"""
        output_path = self.output_dir / filename

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("REFERENCE VALIDATION REPORT\n")
            f.write("=" * 80 + "\n\n")

            # Summary
            total = len(references)
            accessible = sum(1 for ref in references if ref.is_accessible)
            f.write(f"Total References: {total}\n")
            f.write(f"Accessible URLs: {accessible}\n")
            f.write(f"Inaccessible: {total - accessible}\n")
            f.write("\n" + "=" * 80 + "\n\n")

            # Individual references
            for i, ref in enumerate(references, 1):
                f.write(f"[{i}] {'=' * 75}\n\n")

                # Authors
                if ref.authors:
                    f.write("AUTHORS:\n")
                    for author in ref.authors:
                        f.write(f"  - {author}\n")
                    f.write("\n")

                # Title
                if ref.title:
                    f.write(f"TITLE:\n  {ref.title}\n\n")

                # Year
                if ref.year:
                    f.write(f"YEAR: {ref.year}\n\n")

                # DOI
                if ref.doi:
                    f.write(f"DOI: {ref.doi}\n\n")

                # URLs
                if ref.urls:
                    f.write("URLs:\n")
                    for url in ref.urls:
                        f.write(f"  - {url}\n")
                    f.write("\n")

                # Validation Results
                f.write("VALIDATION RESULTS:\n")
                if ref.url_check_results:
                    accessible_urls = ref.url_check_results.get('accessible_urls', [])
                    inaccessible_urls = ref.url_check_results.get('inaccessible_urls', [])
                    match_results = ref.url_check_results.get('match_results', [])

                    if accessible_urls:
                        f.write("  [OK] Accessible URLs:\n")
                        for url in accessible_urls:
                            f.write(f"    - {url}\n")

                    if inaccessible_urls:
                        f.write("  [X] Inaccessible URLs:\n")
                        for url_info in inaccessible_urls:
                            url = url_info.get('url', url_info)
                            reason = url_info.get('reason', 'Unknown') if isinstance(url_info, dict) else 'Unknown'
                            f.write(f"    - {url} ({reason})\n")

                    if match_results:
                        f.write("  Content Matching:\n")
                        for match in match_results:
                            f.write(f"    URL: {match['url']}\n")
                            f.write(f"    Title Match: {match['title_match']}%\n")
                            f.write(f"    Authors Found: {match['authors_found']}\n")
                            if match['author_matches']:
                                for am in match['author_matches']:
                                    f.write(f"      - {am['reference']} → {am['found']}\n")
                else:
                    f.write("  No validation performed\n")

                # Search Results
                if ref.search_results and ref.search_results.get('search_performed'):
                    f.write("\nWEB SEARCH RESULTS:\n")
                    f.write(f"  Search Query: {ref.search_results.get('query', 'N/A')}\n")

                    results = ref.search_results.get('results', [])
                    best_match = ref.search_results.get('best_match')

                    if best_match:
                        f.write(f"\n  [BEST MATCH] Score: {best_match['match_score']}%\n")
                        f.write(f"    URL: {best_match['url']}\n")
                        f.write(f"    Title: {best_match['title']}\n")
                        f.write(f"    Snippet: {best_match['snippet'][:200]}...\n")

                    if results:
                        f.write(f"\n  All Search Results ({len(results)}):\n")
                        for result in results:
                            f.write(f"    [{result['rank']}] Score: {result['match_score']}%\n")
                            f.write(f"        {result['url']}\n")

                f.write("\n" + "-" * 80 + "\n")
                f.write(f"RAW TEXT:\n{ref.raw_text}\n")
                f.write("-" * 80 + "\n\n\n")

        print(f"Text report saved to: {output_path}")
        return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Extract and validate references from research papers (PDF)"
    )
    parser.add_argument(
        'pdf_file',
        type=str,
        help='Path to the PDF file'
    )
    parser.add_argument(
        '-o', '--output-dir',
        type=str,
        default='output',
        help='Output directory for reports (default: output)'
    )
    parser.add_argument(
        '--no-validate',
        action='store_true',
        help='Skip URL validation (only extract references)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=10,
        help='URL request timeout in seconds (default: 10)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=1.0,
        help='Delay between URL requests in seconds (default: 1.0)'
    )
    parser.add_argument(
        '--enable-search',
        action='store_true',
        help='Enable web search for references without URLs'
    )

    args = parser.parse_args()

    # Check if PDF exists
    pdf_path = Path(args.pdf_file)
    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}")
        sys.exit(1)

    print("\n" + "=" * 80)
    print("DOI AND REFERENCE CHECKER")
    print("=" * 80 + "\n")

    # Extract references
    extractor = PDFReferenceExtractor(str(pdf_path))
    extractor.extract_text()

    refs_text = extractor.find_references_section()
    if not refs_text:
        print("Error: Could not find references section in PDF")
        sys.exit(1)

    references = extractor.parse_references(refs_text)

    if not references:
        print("Error: No references were extracted")
        sys.exit(1)

    print(f"\nExtracted {len(references)} references\n")

    # Validate URLs
    if not args.no_validate:
        print("\n" + "=" * 80)
        print("VALIDATING URLS" + (" AND SEARCHING" if args.enable_search else ""))
        print("=" * 80 + "\n")

        validator = URLValidator(timeout=args.timeout, delay=args.delay, enable_search=args.enable_search)

        for i, ref in enumerate(references, 1):
            if ref.urls:
                print(f"\n[{i}/{len(references)}] Validating reference...")
                validator.check_reference(ref)
            elif args.enable_search:
                print(f"\n[{i}/{len(references)}] No URLs found, searching online...")
                validator.check_reference(ref)
            else:
                print(f"\n[{i}/{len(references)}] No URLs found in reference")

    # Generate reports
    print("\n" + "=" * 80)
    print("GENERATING REPORTS")
    print("=" * 80 + "\n")

    output_dir = Path(args.output_dir)
    reporter = ReportGenerator(output_dir)

    reporter.generate_json_report(references)
    reporter.generate_text_report(references)

    print("\n" + "=" * 80)
    print("DONE!")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
