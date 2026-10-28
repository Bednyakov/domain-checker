# python3 generate_prefixes.py string

import argparse
from itertools import product
from pathlib import Path
import string


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepend every two-letter Latin prefix to a string"
    )
    parser.add_argument("text", help="String to add prefixes to")
    parser.add_argument(
        "-o",
        "--output",
        default="prefixed_words.txt",
        help="Output file (default: prefixed_words.txt)",
    )
    args = parser.parse_args()

    prefixes = (
        "".join(letters)
        for letters in product(string.ascii_lowercase, repeat=2)
    )
    results = (prefix + args.text for prefix in prefixes)
    Path(args.output).write_text(
        "\n".join(results) + "\n",
        encoding="utf-8",
    )

    print("Generated 676 strings")
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
