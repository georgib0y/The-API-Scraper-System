import logging
import os
import json

from mdparser import ParseError, parse_request


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

REPO_PATH = "repos"


def main():
    for dirpath, _, filenames in os.walk(REPO_PATH):
        # skip versioned api calls, only concerned with v3 calls atm
        if "version" in dirpath:
            continue

        for filename in filenames:
            if filename == "README.md":
                continue
            if not filename.endswith(".md"):
                continue

            path = os.path.join(dirpath, filename)
            with open(path) as file:
                text = file.read()

            scope = os.path.basename(dirpath)
            logger.info(f"parsing file: {scope}: {text}")

            try:
                res = parse_request(text, scope)
                logger.debug(f"{res}")
                print(json.dumps(res.into_dict(), indent=2))
                print()
            except (ParseError, json.JSONDecodeError) as err:
                logger.error(f"failed to parse {scope}/{filename}")
                raise err


if __name__ == "__main__":
    main()
