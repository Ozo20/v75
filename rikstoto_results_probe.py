from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


RACE_DAY_KEY = "FO_NR_2026-09-19"

URL = (
    "https://www.rikstoto.no/"
    f"Resultater/{RACE_DAY_KEY}"
)

OUTPUT = (
    Path.home()
    / "Downloads"
    / "rikstoto-results-probe-2026-09-19.json"
)


def interesting(url: str, content_type: str) -> bool:
    parsed = urlparse(url)

    # Hold inspeksjonen til Rikstoto.
    if not parsed.netloc.endswith("rikstoto.no"):
        return False

    text = url.lower()
    ct = content_type.lower()

    keywords = (
        "/api/",
        "result",
        "race",
        "start",
        "winner",
        "placing",
        "dividend",
        "payout",
        "pool",
        "game",
    )

    return (
        "json" in ct
        or any(word in text for word in keywords)
    )


def main() -> None:
    captured: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        context = browser.new_context(
            locale="nb-NO",
            user_agent=(
                "Mozilla/5.0 "
                "(Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),
        )

        page = context.new_page()

        def handle_response(response) -> None:
            try:
                content_type = response.headers.get(
                    "content-type",
                    "",
                )

                if not interesting(
                    response.url,
                    content_type,
                ):
                    return

                item = {
                    "status": response.status,
                    "method": response.request.method,
                    "url": response.url,
                    "content_type": content_type,
                }

                if (
                    response.status == 200
                    and "json" in content_type.lower()
                ):
                    try:
                        item["json"] = response.json()
                    except Exception as exc:
                        item["json_error"] = str(exc)

                captured.append(item)

                print(
                    f"{response.status:3} "
                    f"{response.request.method:4} "
                    f"{content_type[:32]:32} "
                    f"{response.url}"
                )

            except Exception as exc:
                print(
                    "Response inspection error:",
                    exc,
                )

        page.on("response", handle_response)

        print("\n=== OPEN RESULTS PAGE ===")
        print(URL)
        print()

        page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60_000,
        )

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
    print(
        "Captured responses:",
        len(captured),
    )
    print(f"Saved to: {OUTPUT}")
    print("=" * 80)


if __name__ == "__main__":
    main()
