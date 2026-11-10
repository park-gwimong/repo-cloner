"""Turn unittest FAIL/ERROR blocks into GitHub Actions error annotations.

Annotations can be read without signing in, unlike the raw job log.
"""

import sys

SEPARATOR = "=" * 70
END = "-" * 70
LIMIT = 10  # GitHub shows at most 10 error annotations per step


def escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_property(text: str) -> str:
    return escape(text).replace(":", "%3A").replace(",", "%2C")


def failures(text: str):
    for block in text.split(SEPARATOR)[1:]:
        head, _, body = block.strip("\n").partition("\n")
        if not head.startswith(("FAIL:", "ERROR:")):
            continue
        body = body.split("\n" + END + "\nRan ")[0].strip("-\n")
        yield head, body


def main() -> None:
    with open(sys.argv[1], encoding="utf-8", errors="replace") as handle:
        found = list(failures(handle.read()))
    for title, body in found[:LIMIT]:
        print(f"::error title={escape_property(title)}::{escape(body[-4000:])}")
    print(f"{len(found)} failing test(s) reported" + (f"; first {LIMIT} shown" if len(found) > LIMIT else ""))


if __name__ == "__main__":
    main()
