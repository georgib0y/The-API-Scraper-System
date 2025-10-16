import logging
import os
import json

from mdparser import parse_request


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

REPO_PATH = "patched_repos"

def main():
    for dirpath, _, filenames in os.walk(REPO_PATH):
        # skip versioned api calls, only concerned with v3 calls atm
        if "version" in dirpath: continue

        for filename in filenames:
            if filename == "README.md": continue
            if not filename.endswith(".md"): continue

            path = os.path.join(dirpath, filename)
            with open(path) as file:
                text = file.read()

            logger.info(f"parsing file: {text}")
            scope = os.path.basename(dirpath)
            res = parse_request(text, scope)
            print(json.dumps(res.into_dict(), indent=2))
            print()


if __name__ == "__main__":
    main()
