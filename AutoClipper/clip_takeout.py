import argparse
import csv
import re
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


# =====================================================
# CONFIGURATION
# =====================================================

VIDEO_TIME_PATTERN = re.compile(
    r"(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})"
)

CLEAR_FLAG = "C"
OCCLUDED_FLAG = "O"
NO_DISTANCE_FLAG = ""


# =====================================================
# EXECUTABLE HELPERS
# =====================================================

def find_executable(name: str) -> str:
    """
    Find ffmpeg/ffprobe from PATH first.

    If not found, also check the user's Downloads folder.
    """

    executable = shutil.which(name)

    if executable:
        return executable

    downloads_candidate = Path.home() / "Downloads" / name

    if downloads_candidate.exists():
        return str(downloads_candidate)

    windows_candidate = downloads_candidate.with_suffix(".exe")

    if windows_candidate.exists():
        return str(windows_candidate)

    raise FileNotFoundError(
        f"Could not find {name}. Add it to PATH or place it in Downloads."
    )


FFMPEG_PATH = find_executable("ffmpeg")
FFPROBE_PATH = find_executable("ffprobe")


# =====================================================
# VIDEO TIMESTAMP HELPERS
# =====================================================

def parse_video_start_time(video_path: Path):
    """
    Parse a Google Takeout filename such as:

    2026_06_12_17_42_08.mp4
    """

    match = VIDEO_TIME_PATTERN.search(video_path.name)

    if not match:
        return None

    year, month, day, hour, minute, second = map(int, match.groups())

    return datetime(
        year,
        month,
        day,
        hour,
        minute,
        second
    )


def parse_csv_time(value: str) -> datetime:
    """
    Parse tracker timestamps such as:

    6/12/2026, 5:46:44 PM
    """

    return datetime.strptime(
        value.strip(),
        "%m/%d/%Y, %I:%M:%S %p"
    )


def get_video_duration_seconds(video_path: Path) -> float:
    command = [
        FFPROBE_PATH,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=nokey=1:noprint_wrappers=1",
        str(video_path)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed for:\n{video_path}\n\n"
            f"{result.stderr}"
        )

    return float(result.stdout.strip())


def build_video_index(video_folder: Path):
    """
    Recursively find every MP4 below the supplied folder.

    This works even when Takeout files remain scattered across
    multiple nested folders.
    """

    videos = []

    for video_path in sorted(video_folder.rglob("*.mp4")):
        start_time = parse_video_start_time(video_path)

        if start_time is None:
            print(
                "Skipping video with an unknown timestamp: "
                f"{video_path.name}"
            )
            continue

        duration = get_video_duration_seconds(video_path)
        end_time = start_time + timedelta(seconds=duration)

        videos.append({
            "path": video_path,
            "start": start_time,
            "end": end_time,
            "duration": duration
        })

    videos.sort(key=lambda video: video["start"])

    return videos


def find_videos_for_clip(videos, clip_start, clip_end):
    """
    Return every source video that overlaps the requested clip.

    This allows one event to cross from one 15-minute Takeout
    segment into the next.
    """

    matches = []

    for video in videos:
        if video["end"] > clip_start and video["start"] < clip_end:
            matches.append(video)

    return matches


# =====================================================
# OUTPUT-NAME PARSING
# =====================================================

def parse_environment_and_time(set_name: str):
    """
    Indoor Day    -> IN, D
    Outdoor Day   -> OUT, D
    Indoor Night  -> IN, N
    Outdoor Night -> OUT, N
    """

    normalized = set_name.strip().lower()

    if "indoor" in normalized:
        environment = "IN"
    elif "outdoor" in normalized:
        environment = "OUT"
    else:
        raise ValueError(
            f"Could not determine environment from set: {set_name}"
        )

    if "day" in normalized:
        time_code = "D"
    elif "night" in normalized:
        time_code = "N"
    else:
        raise ValueError(
            f"Could not determine day/night from set: {set_name}"
        )

    return environment, time_code


def parse_event_name(event_name: str):
    """
    Supported examples:

    C1 0°
    C1 45°
    C1 90°
    C1 Random
    C1 90° Short
    C1 90° Long
    C4 45°

    Rule:
      Original C4 becomes C3 with occlusion flag O.
      C1-C3 use clear flag C.
    """

    normalized = event_name.strip().upper()
    normalized = normalized.replace("°", "")

    clothing_match = re.search(r"\bC\s*([1-4])\b", normalized)

    if not clothing_match:
        raise ValueError(
            f"Could not determine clothing set from event: {event_name}"
        )

    original_clothing = int(clothing_match.group(1))

    if original_clothing == 4:
        clothing_code = "C3"
        occlusion_code = OCCLUDED_FLAG
    else:
        clothing_code = f"C{original_clothing}"
        occlusion_code = CLEAR_FLAG

    if "RANDOM" in normalized:
        angle_code = "R"
    elif re.search(r"\b90\b", normalized):
        angle_code = "90"
    elif re.search(r"\b45\b", normalized):
        angle_code = "45"
    elif re.search(r"\b0\b", normalized):
        angle_code = "0"
    else:
        raise ValueError(
            f"Could not determine angle from event: {event_name}"
        )

    if "SHORT" in normalized:
        distance_code = "S"
    elif "LONG" in normalized:
        distance_code = "L"
    else:
        distance_code = NO_DISTANCE_FLAG

    return (
        clothing_code,
        occlusion_code,
        angle_code,
        distance_code
    )


def create_output_filename(
    set_name: str,
    event_name: str,
    camera_height: str
) -> str:
    environment, time_code = parse_environment_and_time(set_name)

    (
        clothing_code,
        occlusion_code,
        angle_code,
        distance_code
    ) = parse_event_name(event_name)

    parts = [
        environment,
        time_code,
        clothing_code,
        occlusion_code,
        angle_code,
        camera_height
    ]

    if distance_code:
        parts.append(distance_code)

    return "-".join(parts) + ".mp4"


# =====================================================
# PARTICIPANT ANONYMIZATION
# =====================================================

def build_participant_codes(rows):
    """
    Assign anonymous participant folder names:

    First participant  -> P001
    Second participant -> P002
    """

    codes = {}
    next_number = 1

    for row in rows:
        original_name = row["Participant"].strip()

        if original_name not in codes:
            codes[original_name] = f"P{next_number:03d}"
            next_number += 1

    return codes


# =====================================================
# VIDEO CLIPPING
# =====================================================

def clip_video(
    input_video: Path,
    output_video: Path,
    start_offset_seconds: float,
    duration_seconds: float
):
    """
    Re-encode each temporary piece so all pieces have compatible
    formats before concatenation.
    """

    command = [
        FFMPEG_PATH,
        "-y",
        "-ss", str(start_offset_seconds),
        "-i", str(input_video),
        "-t", str(duration_seconds),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "veryfast",
        "-movflags", "+faststart",
        str(output_video)
    ]

    subprocess.run(command, check=True)


def concat_videos(part_paths, output_path: Path):
    list_file = output_path.parent / (
        f"{output_path.stem}_parts.txt"
    )

    with open(
        list_file,
        "w",
        encoding="utf-8"
    ) as file:
        for part_path in part_paths:
            escaped_path = (
                str(part_path.resolve())
                .replace("\\", "/")
                .replace("'", "'\\''")
            )

            file.write(f"file '{escaped_path}'\n")

    command = [
        FFMPEG_PATH,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output_path)
    ]

    try:
        subprocess.run(command, check=True)
    finally:
        if list_file.exists():
            list_file.unlink()


def clip_across_videos(
    matching_videos,
    output_path: Path,
    clip_start: datetime,
    clip_end: datetime
):
    matching_videos = sorted(
        matching_videos,
        key=lambda video: video["start"]
    )

    temp_parts = []

    for index, video in enumerate(matching_videos, start=1):
        part_start_time = max(
            clip_start,
            video["start"]
        )

        part_end_time = min(
            clip_end,
            video["end"]
        )

        if part_end_time <= part_start_time:
            continue

        start_offset = (
            part_start_time - video["start"]
        ).total_seconds()

        duration = (
            part_end_time - part_start_time
        ).total_seconds()

        part_path = output_path.parent / (
            f".{output_path.stem}_part{index}.mp4"
        )

        clip_video(
            input_video=video["path"],
            output_video=part_path,
            start_offset_seconds=start_offset,
            duration_seconds=duration
        )

        temp_parts.append(part_path)

    if not temp_parts:
        return False

    try:
        if len(temp_parts) == 1:
            temp_parts[0].replace(output_path)
        else:
            concat_videos(temp_parts, output_path)
    finally:
        for part_path in temp_parts:
            if part_path.exists():
                part_path.unlink()

    return True


# =====================================================
# FILE HELPERS
# =====================================================

def create_unique_output_path(
    participant_folder: Path,
    output_filename: str
) -> Path:
    """
    Avoid overwriting a previous clip when two rows create the same
    formatted filename.
    """

    output_path = participant_folder / output_filename

    if not output_path.exists():
        return output_path

    stem = output_path.stem
    suffix = output_path.suffix
    counter = 2

    while True:
        candidate = participant_folder / (
            f"{stem}-{counter}{suffix}"
        )

        if not candidate.exists():
            return candidate

        counter += 1


def write_error_csv(path: Path, rows):
    if not rows:
        return

    with open(
        path,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=rows[0].keys()
        )

        writer.writeheader()
        writer.writerows(rows)


# =====================================================
# MAIN
# =====================================================

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--videos",
        required=True,
        help=(
            "Folder containing Google Takeout MP4 videos. "
            "All subfolders are searched."
        )
    )

    parser.add_argument(
        "--csv",
        required=True,
        help="Tracker CSV export"
    )

    parser.add_argument(
        "--output",
        default="output_clips",
        help="Output folder"
    )

    parser.add_argument(
        "--offset-seconds",
        type=float,
        default=0,
        help=(
            "Camera timestamp adjustment. "
            "Positive moves requested clips later."
        )
    )

    parser.add_argument(
        "--participant",
        default=None,
        help="Optional original participant-name filter"
    )

    parser.add_argument(
        "--set",
        default=None,
        help='Optional set filter, such as "Indoor Day"'
    )

    parser.add_argument(
        "--camera-height",
        required=True,
        choices=["MNT", "TAB"],
        help="MNT for mounted camera or TAB for table camera"
    )

    args = parser.parse_args()

    video_folder = Path(args.videos).expanduser()
    csv_path = Path(args.csv).expanduser()
    output_folder = Path(args.output).expanduser()

    if not video_folder.exists():
        raise FileNotFoundError(
            f"Video folder does not exist: {video_folder}"
        )

    if not csv_path.exists():
        raise FileNotFoundError(
            f"CSV does not exist: {csv_path}"
        )

    output_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    print("Reading tracker CSV...")

    with open(
        csv_path,
        newline="",
        encoding="utf-8-sig"
    ) as file:
        rows = list(csv.DictReader(file))

    participant_codes = build_participant_codes(rows)

    print("Indexing videos...")
    videos = build_video_index(video_folder)
    print(f"Found {len(videos)} videos.")

    print("\nVideos near 2026-07-15 00:30:00:")

    debug_time = datetime(2026, 7, 15, 0, 30, 0)

    for video in videos:
        difference = abs(
            (video["start"] - debug_time).total_seconds()
        )

        if difference <= 120:
            print(
                video["path"],
                "|",
                video["start"],
                "->",
                video["end"],
                "| duration:",
                video["duration"]
            )

    print()
    
    created_count = 0
    missed_rows = []
    naming_error_rows = []

    for row in rows:
        if row["Status"].strip().lower() != "completed":
            continue

        original_participant = row["Participant"].strip()

        if (
            args.participant
            and original_participant != args.participant
        ):
            continue

        if (
            args.set
            and row["Set"].strip() != args.set
        ):
            continue

        participant_code = participant_codes[
            original_participant
        ]

        try:
            clip_start = (
                parse_csv_time(row["Clip Start"])
                + timedelta(seconds=args.offset_seconds)
            )

            clip_end = (
                parse_csv_time(row["Clip End"])
                + timedelta(seconds=args.offset_seconds)
            )
        except ValueError as error:
            missed_rows.append({
                **row,
                "Reason": f"Invalid timestamp: {error}"
            })

            print(
                f"TIMESTAMP ERROR: {participant_code} "
                f"{row['Set']} {row['Event']}"
            )
            continue

        if clip_end <= clip_start:
            missed_rows.append({
                **row,
                "Reason": "Clip End was not after Clip Start"
            })
            continue

        matching_videos = find_videos_for_clip(
            videos,
            clip_start,
            clip_end
        )

        if not matching_videos:
            missed_rows.append({
                **row,
                "Reason": (
                    "No Takeout video overlapped the requested time"
                )
            })

            print(
                f"MISS: {participant_code} "
                f"{row['Set']} {row['Event']} "
                f"{clip_start} -> {clip_end}"
            )
            continue

        try:
            output_filename = create_output_filename(
                set_name=row["Set"],
                event_name=row["Event"],
                camera_height=args.camera_height
            )
        except ValueError as error:
            naming_error_rows.append({
                **row,
                "Naming Error": str(error)
            })

            print(
                f"NAMING ERROR: {participant_code} "
                f"{row['Event']} — {error}"
            )
            continue

        participant_folder = (
            output_folder / participant_code
        )

        participant_folder.mkdir(
            parents=True,
            exist_ok=True
        )

        output_path = create_unique_output_path(
            participant_folder,
            output_filename
        )

        print(
            f"Clipping {participant_code}/{output_path.name} "
            f"from {len(matching_videos)} video file(s)"
        )

        success = clip_across_videos(
            matching_videos=matching_videos,
            output_path=output_path,
            clip_start=clip_start,
            clip_end=clip_end
        )

        if not success:
            missed_rows.append({
                **row,
                "Reason": "No valid overlapping video segment"
            })
            continue

        created_count += 1

    print()
    print(f"Done. Created {created_count} clips.")
    print(f"Missed: {len(missed_rows)}")
    print(f"Naming errors: {len(naming_error_rows)}")

    write_error_csv(
        output_folder / "missed_clips.csv",
        missed_rows
    )

    write_error_csv(
        output_folder / "naming_errors.csv",
        naming_error_rows
    )

    mapping_path = (
        output_folder / "participant_mapping.csv"
    )

    with open(
        mapping_path,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.writer(file)

        writer.writerow([
            "Anonymous Participant",
            "Original Participant"
        ])

        for original_name, code in participant_codes.items():
            writer.writerow([
                code,
                original_name
            ])

    print(
        "Private participant mapping saved to: "
        f"{mapping_path}"
    )


if __name__ == "__main__":
    main()