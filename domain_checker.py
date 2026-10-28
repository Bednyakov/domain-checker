
# pip install dnspython
import argparse
import asyncio
from pathlib import Path

import dns.asyncresolver
import dns.exception
import dns.resolver


RECORD_TYPES = ("NS", "A", "AAAA", "MX", "CNAME", "TXT", "CAA")


async def check_domain(
    domain: str,
    resolver: dns.asyncresolver.Resolver,
    semaphore: asyncio.Semaphore,
) -> tuple[str, str]:
    async with semaphore:
        for record_type in RECORD_TYPES:
            try:
                await resolver.resolve(
                    domain,
                    record_type,
                    lifetime=3,
                    raise_on_no_answer=False,
                )
                # Даже ответ без записей означает, что имя может существовать.
                return domain, "dns_exists"

            except dns.resolver.NXDOMAIN:
                # Проверяем следующие типы: домен может иметь
                # особенности DNS-ответов у разных типов записей.
                continue

            except dns.resolver.NoNameservers:
                return domain, "unknown"

            except (dns.exception.Timeout, dns.resolver.NoAnswer):
                # Таймаут не доказывает отсутствие домена.
                return domain, "unknown"

            except dns.exception.DNSException:
                return domain, "unknown"

        return domain, "no_dns"


async def main():
    parser = argparse.ArgumentParser(
        description="Find domains without DNS records"
    )
    parser.add_argument("words", help="File with words, one per line")
    parser.add_argument("zone", help="Domain zone, e.g. com, dev, ru")
    parser.add_argument(
        "-o", "--output",
        default="available_candidates.txt",
        help="Output file",
    )
    parser.add_argument(
        "-c", "--concurrency",
        type=int,
        default=30,
        help="Maximum concurrent checks",
    )
    args = parser.parse_args()

    zone = args.zone.strip().lstrip(".")
    if not zone or "/" in zone:
        parser.error("Invalid domain zone")

    words = Path(args.words).read_text(encoding="utf-8").splitlines()
    domains = sorted({
        f"{word.strip().lower().rstrip('.').lstrip('.')}."
        f"{zone}"
        for word in words
        if word.strip()
    })

    resolver = dns.asyncresolver.Resolver()
    semaphore = asyncio.Semaphore(max(1, args.concurrency))

    results = await asyncio.gather(*(
        check_domain(domain, resolver, semaphore)
        for domain in domains
    ))

    candidates = sorted(
        domain for domain, status in results
        if status == "no_dns"
    )
    unknown = sorted(
        domain for domain, status in results
        if status == "unknown"
    )

    Path(args.output).write_text(
        "\n".join(candidates) + ("\n" if candidates else ""),
        encoding="utf-8",
    )

    print(f"Checked: {len(domains)}")
    print(f"No DNS records (candidates): {len(candidates)}")
    print(f"DNS errors / unknown: {len(unknown)}")
    print(f"Saved to: {args.output}")

    if unknown:
        print("\nCould not verify:")
        print("\n".join(unknown))


if __name__ == "__main__":
    asyncio.run(main())
