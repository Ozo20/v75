from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


OUTPUT = Path.home() / "Downloads" / "rikstoto-network-probe.json"

# Historisk offentlig spillside som vi vet inneholder løpsdata.
URL = "https://www.rikstoto.no/Spill/S2_NR_2026-09-29/V?race=9"


def looks_interesting(url: str, content_type: str) -> bool:
    url_lower = url.lower()
    ct_lower = content_type.lower()

    keywords = (
        "api",
        "graphql",
        "race",
        "runner",
        "horse",
        "start",
        "program",
        "bet",
        "game",
        "meeting",
    )

    return (
        "json" in ct_lower
        or "graphql" in ct_lower
        or any(word in url_lower for word in keywords)
    )


def main() -> None:
    captured: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        context = browser.new_context(
            locale="nb-NO",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),
        )

        page = context.new_page()

        def handle_response(response) -> None:
            try:
                headers = response.headers
                content_type = headers.get("content-type", "")

                if not looks_interesting(response.url, content_type):
                    return

                item = {
                    "status": response.status,
                    "url": response.url,
                    "content_type": content_type,
                    "domain": urlparse(response.url).netloc,
                }

                if "json" in content_type.lower():
                    try:
                        body = response.json()

                        # Ikke dump enorme objekter ukontrollert.
                        encoded = json.dumps(
                            body,
                            ensure_ascii=False,
                            default=str,
                        )

                        if len(encoded) <= 100_000:
                            item["json"] = body
                        else:
                            item["json_preview"] = encoded[:20_000]
                            item["json_size"] = len(encoded)

                    except Exception as exc:
                        item["json_error"] = str(exc)

                captured.append(item)

                print(
                    f"{response.status:3} "
                    f"{content_type[:30]:30} "
                    f"{response.url}"
                )

            except Exception as exc:
                print("Response inspection error:", exc)

        page.on("response", handle_response)

        print(f"\nOpening:\n{URL}\n")

        page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60_000,
        )

        # La bakgrunnskallene på siden bli ferdige.
        page.wait_for_timeout(10_000)

        print("\nPage title:", page.title())
        print("Final URL:", page.url)

        browser.close()

    OUTPUT.write_text(
        json.dumps(
            captured,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 80)
    print(f"Captured interesting responses: {len(captured)}")
    print(f"Saved to: {OUTPUT}")
    print("=" * 80)


if __name__ == "__main__":
    main()
