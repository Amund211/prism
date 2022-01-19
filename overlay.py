from pathlib import Path

from examples.sidelay.__main__ import main

if __name__ == "__main__":
    main(Path(__file__).parent.resolve() / "data" / "nick_database.json")
