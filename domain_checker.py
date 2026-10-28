
# pip install dnspython
import argparse
import asyncio
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

import dns.asyncresolver
import dns.exception
import dns.resolver


RECORD_TYPES = ("NS", "A", "AAAA", "MX", "CNAME", "TXT", "CAA")
RDAP_BOOTSTRAP_URL = "https://data.iana.org/rdap/dns.json"
HTTP_TIMEOUT = 5


def load_rdap_bootstrap() -> dict[str, list[str]]:
    request = urllib.request.Request(
        RDAP_BOOTSTRAP_URL,
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        bootstrap = json.load(response)

    if not isinstance(bootstrap, dict):
        raise ValueError("Invalid RDAP bootstrap response")
    services = bootstrap.get("services")
    if not isinstance(services, list):
        raise ValueError("Invalid RDAP bootstrap response")

    suffixes: dict[str, list[str]] = {}
    for service in services:
        if (
            not isinstance(service, list)
            or len(service) != 2
            or not isinstance(service[0], list)
            or not isinstance(service[1], list)
        ):
            continue
        urls = [
            url.rstrip("/") + "/"
            for url in service[1]
            if isinstance(url, str) and url.startswith("https://")
        ]
        if not urls:
            continue
        for suffix in service[0]:
            if isinstance(suffix, str):
                suffixes[suffix.lower().lstrip(".")] = urls

    if not suffixes:
        raise ValueError("RDAP bootstrap contains no HTTPS services")
    return suffixes


def find_rdap_base_url(
    domain: str,
    bootstrap: dict[str, list[str]],
) -> str | None:
    labels = domain.rstrip(".").lower().split(".")
    for offset in range(len(labels)):
        suffix = ".".join(labels[offset:])
        urls = bootstrap.get(suffix)
        if urls:
            return urls[0]
    return None


def query_rdap(domain: str, base_url: str) -> str:
    try:
        ascii_domain = domain.rstrip(".").encode("idna").decode("ascii")
        url = (
            base_url
            + "domain/"
            + urllib.parse.quote(ascii_domain, safe=".-")
        )
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/rdap+json",
                "User-Agent": "domain-checker/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            if response.status == 200:
                return "registered"
            return "unknown"
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return "not_registered"
        return "unknown"
    except (OSError, UnicodeError, ValueError):
        return "unknown"


async def check_rdap(
    domain: str,
    bootstrap: dict[str, list[str]],
    semaphore: asyncio.Semaphore,
) -> tuple[str, str]:
    base_url = find_rdap_base_url(domain, bootstrap)
    if base_url is None:
        return domain, "unknown"

    async with semaphore:
        status = await asyncio.to_thread(query_rdap, domain, base_url)
    return domain, status


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

    no_dns = sorted(domain for domain, status in results if status == "no_dns")
    unknown = sorted(
        domain for domain, status in results
        if status == "unknown"
    )

    rdap_bootstrap = None
    rdap_bootstrap_error = None
    if no_dns:
        try:
            rdap_bootstrap = await asyncio.to_thread(load_rdap_bootstrap)
        except (OSError, ValueError) as error:
            rdap_bootstrap_error = str(error)

    if rdap_bootstrap is None:
        rdap_results = [(domain, "unknown") for domain in no_dns]
    else:
        rdap_results = await asyncio.gather(*(
            check_rdap(domain, rdap_bootstrap, semaphore)
            for domain in no_dns
        ))

    candidates = sorted(
        domain for domain, status in rdap_results
        if status == "not_registered"
    )
    rdap_registered = sorted(
        domain for domain, status in rdap_results
        if status == "registered"
    )
    rdap_unknown = sorted(
        domain for domain, status in rdap_results
        if status == "unknown"
    )

    Path(args.output).write_text(
        "\n".join(candidates) + ("\n" if candidates else ""),
        encoding="utf-8",
    )

    print(f"Checked: {len(domains)}")
    print(f"No DNS records: {len(no_dns)}")
    print(f"RDAP confirms unregistered (candidates): {len(candidates)}")
    print(f"RDAP registered: {len(rdap_registered)}")
    print(f"RDAP errors / unknown: {len(rdap_unknown)}")
    print(f"DNS errors / unknown: {len(unknown)}")
    print(f"Saved to: {args.output}")

    if rdap_bootstrap_error:
        print(f"\nCould not load RDAP bootstrap: {rdap_bootstrap_error}")
    if rdap_registered:
        print("\nRegistered according to RDAP:")
        print("\n".join(rdap_registered))
    if rdap_unknown:
        print("\nCould not verify with RDAP:")
        print("\n".join(rdap_unknown))
    if unknown:
        print("\nCould not verify:")
        print("\n".join(unknown))


if __name__ == "__main__":
    asyncio.run(main())
