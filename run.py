from aipro.env_loader import load_env_file
from telegram import launch


if __name__ == "__main__":
    load_env_file()
    raise SystemExit(launch())
