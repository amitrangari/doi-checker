#!/usr/bin/env python3
"""
Example usage of the DOI Checker as a library
"""

from pathlib import Path
from doi_checker import PDFReferenceExtractor, URLValidator, ReportGenerator


def example_extract_only(pdf_path):
    """Example: Extract references without validation"""
    print("Example 1: Extract references only (no validation)")
    print("-" * 60)

    extractor = PDFReferenceExtractor(pdf_path)
    extractor.extract_text()
    refs_text = extractor.find_references_section()

    if refs_text:
        references = extractor.parse_references(refs_text)
        print(f"Found {len(references)} references\n")

        for i, ref in enumerate(references[:3], 1):  # Show first 3
            print(f"Reference {i}:")
            print(f"  Authors: {ref.authors}")
            print(f"  Title: {ref.title}")
            print(f"  DOI: {ref.doi}")
            print(f"  URLs: {ref.urls}")
            print()

    return references


def example_validate_one_reference(pdf_path):
    """Example: Validate just one reference"""
    print("\nExample 2: Validate a single reference")
    print("-" * 60)

    extractor = PDFReferenceExtractor(pdf_path)
    extractor.extract_text()
    refs_text = extractor.find_references_section()

    if refs_text:
        references = extractor.parse_references(refs_text)

        if references and references[0].urls:
            validator = URLValidator(timeout=10, delay=0.5)
            results = validator.check_reference(references[0])

            print(f"\nValidation results:")
            print(f"  Accessible URLs: {len(results['accessible_urls'])}")
            print(f"  Inaccessible URLs: {len(results['inaccessible_urls'])}")

            if results['match_results']:
                for match in results['match_results']:
                    print(f"\n  Match for {match['url']}:")
                    print(f"    Title match: {match['title_match']}%")
                    print(f"    Authors found: {match['authors_found']}")


def example_custom_report(pdf_path):
    """Example: Generate custom analysis"""
    print("\nExample 3: Custom analysis")
    print("-" * 60)

    extractor = PDFReferenceExtractor(pdf_path)
    extractor.extract_text()
    refs_text = extractor.find_references_section()

    if refs_text:
        references = extractor.parse_references(refs_text)

        # Count references with DOI
        with_doi = sum(1 for ref in references if ref.doi)
        with_url = sum(1 for ref in references if ref.urls)
        avg_authors = sum(len(ref.authors) for ref in references) / len(references) if references else 0

        print(f"\nStatistics:")
        print(f"  Total references: {len(references)}")
        print(f"  With DOI: {with_doi} ({with_doi/len(references)*100:.1f}%)")
        print(f"  With URL: {with_url} ({with_url/len(references)*100:.1f}%)")
        print(f"  Average authors per paper: {avg_authors:.1f}")

        # Find year distribution
        years = {}
        for ref in references:
            if ref.year:
                years[ref.year] = years.get(ref.year, 0) + 1

        if years:
            print(f"\n  Year distribution:")
            for year in sorted(years.keys(), reverse=True)[:5]:
                print(f"    {year}: {years[year]} papers")


def main():
    # Replace with your PDF path
    pdf_path = "sample_paper.pdf"

    # Check if file exists
    if not Path(pdf_path).exists():
        print(f"Error: {pdf_path} not found")
        print("Please provide a valid PDF path in the script")
        return

    # Run examples
    references = example_extract_only(pdf_path)
    example_validate_one_reference(pdf_path)
    example_custom_report(pdf_path)


if __name__ == "__main__":
    main()
