import argparse
import re
from pathlib import Path


# =====================================================
# OLD FILENAME PATTERN
# =====================================================

# Supported examples:
#
# 001_Indoor_Day_C1_0.mp4
# 001_PersonName_Indoor_Day_C1_0.mp4
# 001_Outdoor_Night_C1_90_Short.mp4
# 001_Outdoor_Night_C1_90_Long.mp4
# 001_Indoor_Day_C4_45.mp4
# 001_Indoor_Day_C1_Random.mp4

OLD_NAME_PATTERN = re.compile(
    r"""
    ^
    (?:(?P<number>\d+)_)?                 # Optional number: 001_
    (?:(?P<participant>.*?)_)?            # Optional old participant name
    (?P<environment>Indoor|Outdoor)_
    (?P<time>Day|Night)_
    (?P<clothing>C[1-4])_
    (?P<angle>0|45|90|Random)
    (?:_(?P<distance>Short|Long|S|L))?
    \.mp4
    $
    """,
    re.IGNORECASE | re.VERBOSE
)


# =====================================================
# CAMERA-HEIGHT DETECTION
# =====================================================

def detect_camera_height(video_path: Path) -> str | None:
    """
    Detect TAB or MNT using any folder name above the video.

    Recognized table names:
      Table, TAB, Table Camera

    Recognized mounted names:
      Mounted, MNT, Mounted Camera
    """

    parent_names = [
        parent.name.lower()
        for parent in video_path.parents
    ]

    for name in parent_names:
        if (
            name == "tab"
            or "table" in name
        ):
            return "TAB"

        if (
            name == "mnt"
            or "mount" in name
        ):
            return "MNT"

    return None


# =====================================================
# NEW FILENAME CREATION
# =====================================================

def build_new_name(match, camera_height: str) -> str:
    environment = match.group("environment").lower()
    time_period = match.group("time").lower()
    clothing = match.group("clothing").upper()
    angle = match.group("angle")
    distance = match.group("distance")

    environment_code = (
        "IN" if environment == "indoor" else "OUT"
    )

    time_code = (
        "D" if time_period == "day" else "N"
    )

    # C4 represents clothing set 3 with occlusion.
    if clothing == "C4":
        clothing_code = "C3"
        occlusion_code = "O"
    else:
        clothing_code = clothing
        occlusion_code = "C"

    angle_code = (
        "R" if angle.lower() == "random" else angle
    )

    filename_parts = [
        environment_code,
        time_code,
        clothing_code,
        occlusion_code,
        angle_code,
        camera_height
    ]

    # Only add a distance flag for actual short/long shots.
    if distance:
        normalized_distance = distance.upper()

        if normalized_distance in {"SHORT", "S"}:
            filename_parts.append("S")
        elif normalized_distance in {"LONG", "L"}:
            filename_parts.append("L")

    return "-".join(filename_parts) + ".mp4"


def make_unique_path(path: Path) -> Path:
    """
    Prevent accidental replacement when a filename already exists.
    """

    if not path.exists():
        return path

    counter = 2

    while True:
        candidate = path.with_name(
            f"{path.stem}-{counter}{path.suffix}"
        )

        if not candidate.exists():
            return candidate

        counter += 1


# =====================================================
# MAIN RENAMING PROCESS
# =====================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Rename clips inside participant folders using "
            "the new dataset naming convention."
        )
    )

    parser.add_argument(
        "--folder",
        required=True,
        help=(
            "Main folder containing P1, P2, P3, and their "
            "Table/Mounted subfolders"
        )
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview all changes without renaming files"
    )

    args = parser.parse_args()

    root_folder = Path(args.folder).expanduser().resolve()

    if not root_folder.exists():
        raise FileNotFoundError(
            f"Folder does not exist: {root_folder}"
        )

    renamed_count = 0
    skipped_count = 0
    height_error_count = 0

    for video_path in sorted(root_folder.rglob("*.mp4")):
        match = OLD_NAME_PATTERN.match(video_path.name)

        if not match:
            print(f"SKIP NAME: {video_path}")
            skipped_count += 1
            continue

        camera_height = detect_camera_height(video_path)

        if camera_height is None:
            print(
                f"SKIP HEIGHT: Could not determine TAB/MNT for "
                f"{video_path}"
            )
            height_error_count += 1
            continue

        new_name = build_new_name(
            match=match,
            camera_height=camera_height
        )

        new_path = make_unique_path(
            video_path.with_name(new_name)
        )

        relative_old = video_path.relative_to(root_folder)
        relative_new = new_path.relative_to(root_folder)

        print(f"{relative_old}")
        print(f"  -> {relative_new}")

        if not args.dry_run:
            video_path.rename(new_path)

        renamed_count += 1

    print()
    print("Finished")
    print(f"Matched: {renamed_count}")
    print(f"Skipped because of filename: {skipped_count}")
    print(f"Skipped because TAB/MNT was unknown: {height_error_count}")

    if args.dry_run:
        print("Dry run only. No files were changed.")


if __name__ == "__main__":
    main()