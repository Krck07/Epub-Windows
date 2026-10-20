"""Create sample_book.epub in the current folder — handy for first-time testing.

Usage:  python make_sample_book.py [output.epub]
"""
import sys

from epub_reader.sample import build_sample_book

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "sample_book.epub"
    build_sample_book(out)
    print(f"Sample book written to {out}")
