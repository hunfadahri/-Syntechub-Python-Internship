import argparse
import os
import shutil

# Which extensions go into which folder
FOLDERS = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".webp"],
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".xlsx", ".csv", ".pptx"],
    "Audio": [".mp3", ".wav"],
    "Video": [".mp4", ".mkv", ".avi"],
    "Archives": [".zip", ".rar", ".7z"],
}


def get_folder(filename):
    ext = os.path.splitext(filename)[1].lower()
    for folder, extensions in FOLDERS.items():
        if ext in extensions:
            return folder
    return "Others"


def organize(path, dry_run):
    log = None if dry_run else open("organizer_log.txt", "a", encoding="utf-8")
    try:
        for name in os.listdir(path):
            src = os.path.join(path, name)

            if not os.path.isfile(src):
                continue  # skip folders

            dest_folder = os.path.join(path, get_folder(name))
            dest = os.path.join(dest_folder, name)

            # If a file with the same name exists, add _1, _2, ...
            base, ext = os.path.splitext(name)
            count = 1
            while os.path.exists(dest):
                dest = os.path.join(dest_folder, f"{base}_{count}{ext}")
                count += 1

            message = f"{src}  ->  {dest}"
            if dry_run:
                print("WOULD MOVE:", message)
            else:
                os.makedirs(dest_folder, exist_ok=True)
                shutil.move(src, dest)
                print("MOVED:", message)
                if log is not None:
                    log.write(message + "\n")
    finally:
        if log is not None:
            log.close()


def main():
    parser = argparse.ArgumentParser(
        description="Organize files into folders based on their extensions."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        help="Folder to organize (defaults to your Downloads folder)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Preview moves without changing files",
    )
    mode.add_argument(
        "--live",
        dest="dry_run",
        action="store_false",
        help="Move files instead of previewing",
    )
    parser.set_defaults(dry_run=None)
    args = parser.parse_args()

    try:
        folder = args.folder or os.path.join(os.path.expanduser("~"), "Downloads")
        if args.folder is None:
            print(f"No folder specified; using Downloads: {folder}")

        folder = os.path.abspath(os.path.expanduser(folder))
        if not os.path.isdir(folder):
            print(f"That folder does not exist: {folder}")
            return 1

        dry_run = args.dry_run if args.dry_run is not None else True

        organize(folder, dry_run=dry_run)
        print("Done.")
        return 0
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())