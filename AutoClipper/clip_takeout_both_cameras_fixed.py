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

# Map the two physical camera folder names once here.
# Replace the MNT placeholder with the actual mounted-camera folder ID.
CAMERA_MAP = {
    "63091Z8A90HU1H": "TAB",
    "63101Z8A90HUF0": "MNT",
}


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



def find_camera_folders(root_folder: Path):
    """
    Find exactly one folder for each physical camera.

    If duplicate camera folders exist under both:

        Nest/camera/...
        Nest/Nest/camera/...

    prefer the folder with the shorter path, which is normally:

        Nest/camera/...
    """

    result = {"TAB": [], "MNT": []}

    for camera_id, camera_height in CAMERA_MAP.items():
        matches = [
            path
            for path in root_folder.rglob(camera_id)
            if path.is_dir()
        ]

        if not matches:
            print(
                f"WARNING: Could not find {camera_height} camera "
                f"folder ID: {camera_id}"
            )
            continue

        # Prefer the least deeply nested matching folder.
        matches.sort(
            key=lambda path: (
                len(path.relative_to(root_folder).parts),
                len(str(path))
            )
        )

        selected = matches[0]

        result[camera_height] = [selected]

        print(
            f"Using {camera_height} camera folder: "
            f"{selected}"
        )

        if len(matches) > 1:
            for ignored in matches[1:]:
                print(
                    f"Ignoring duplicate {camera_height} camera folder: "
                    f"{ignored}"
                )

    return result

def build_camera_video_index(camera_folders):
    """
    Build a video index for one physical camera.

    Normally camera_folders now contains exactly one selected folder.
    A timestamp-and-duration safeguard still prevents duplicate source
    recordings from being indexed.
    """

    videos = []
    seen_videos = set()

    for camera_folder in camera_folders:
        for video_path in sorted(camera_folder.rglob("*.mp4")):
            start_time = parse_video_start_time(video_path)

            if start_time is None:
                print(
                    "Skipping video with unknown timestamp: "
                    f"{video_path}"
                )
                continue

            try:
                duration = get_video_duration_seconds(video_path)
            except (RuntimeError, ValueError) as error:
                print(
                    f"Skipping unreadable video: {video_path}\n"
                    f"Reason: {error}"
                )
                continue

            duplicate_key = (
                start_time,
                round(duration, 3)
            )

            if duplicate_key in seen_videos:
                print(
                    "Skipping duplicate source video: "
                    f"{video_path}"
                )
                continue

            seen_videos.add(duplicate_key)

            videos.append({
                "path": video_path,
                "start": start_time,
                "end": start_time + timedelta(seconds=duration),
                "duration": duration
            })

    videos.sort(key=lambda video: video["start"])

    return videos


def find_videos_for_clip(videos, clip_start, clip_end):
    """
    Return source videos overlapping the requested clip while
    preventing duplicate Takeout copies from being returned.
    """

    matches = []
    seen_segments = set()

    for video in videos:
        if not (
            video["end"] > clip_start
            and video["start"] < clip_end
        ):
            continue

        segment_key = (
            video["start"],
            round(video["duration"], 3)
        )

        if segment_key in seen_segments:
            continue

        seen_segments.add(segment_key)
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


def has_video_stream(video_path: Path) -> bool:
    """
    Confirm that a temporary MP4 exists and contains a readable video stream.
    """

    if not video_path.exists() or video_path.stat().st_size == 0:
        return False

    command = [
        FFPROBE_PATH,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_type",
        "-of", "default=nokey=1:noprint_wrappers=1",
        str(video_path)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    return (
        result.returncode == 0
        and "video" in result.stdout.lower()
    )


def concat_videos(part_paths, output_path: Path):
    """
    Join temporary pieces with FFmpeg's concat filter.

    This re-encodes the final result instead of using the concat demuxer
    with "-c copy", which is more reliable when Takeout segments have
    slightly different timestamps or container metadata.
    """

    valid_parts = [
        part_path
        for part_path in part_paths
        if has_video_stream(part_path)
    ]

    if not valid_parts:
        raise RuntimeError(
            "None of the temporary clip pieces contained a valid video stream."
        )

    if len(valid_parts) == 1:
        valid_parts[0].replace(output_path)
        return

    command = [FFMPEG_PATH, "-y"]

    for part_path in valid_parts:
        command.extend(["-i", str(part_path)])

    video_inputs = "".join(
        f"[{index}:v:0]"
        for index in range(len(valid_parts))
    )

    filter_complex = (
        f"{video_inputs}"
        f"concat=n={len(valid_parts)}:v=1:a=0[v]"
    )

    command.extend([
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path)
    ])

    subprocess.run(command, check=True)


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

    try:
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

            # Ignore tiny edge-overlaps caused by fractional durations.
            if duration < 0.1:
                continue

            part_path = output_path.parent / (
                f".{output_path.stem}_part{index}.mp4"
            )

            clip_video(
                input_video=video["path"],
                output_video=part_path,
                start_offset_seconds=start_offset,
                duration_seconds=duration
            )

            if (
                not part_path.exists()
                or part_path.stat().st_size == 0
            ):
                continue

            if not has_video_stream(part_path):
                print(
                    "WARNING: Ignoring invalid temporary piece: "
                    f"{part_path.name}"
                )
                if part_path.exists():
                    part_path.unlink()
                continue

            temp_parts.append(part_path)

        if not temp_parts:
            return False

        if len(temp_parts) == 1:
            temp_parts[0].replace(output_path)
            temp_parts.clear()
        else:
            concat_videos(temp_parts, output_path)

        return has_video_stream(output_path)

    finally:
        for part_path in temp_parts:
            if part_path.exists():
                part_path.unlink()


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
            "Higher-level Takeout/Nest folder containing both mapped camera folders. "
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
        "--skip-existing",
        action="store_true",
        help="Skip clips that already exist and only create missing outputs"
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

    print("Finding mapped camera folders...")
    camera_folders = find_camera_folders(video_folder)

    camera_video_indices = {}

    for camera_height in ("TAB", "MNT"):
        folders = camera_folders[camera_height]

        if not folders:
            continue

        print(f"Indexing {camera_height} camera videos...")
        camera_videos = build_camera_video_index(folders)
        camera_video_indices[camera_height] = camera_videos
        print(f"Found {len(camera_videos)} {camera_height} videos.")

    if not camera_video_indices:
        discovered = sorted({
            path.name
            for path in video_folder.rglob("*")
            if path.is_dir() and re.fullmatch(r"[A-Z0-9]{10,}", path.name)
        })

        raise RuntimeError(
            "No mapped camera folders were found. "
            "Update CAMERA_MAP near the top of the script. "
            f"Discovered possible camera IDs: {discovered}"
        )

    created_count = 0
    missed_rows = []
    naming_error_rows = []

    for camera_height, videos in camera_video_indices.items():
        print()
        print(f"Processing {camera_height} camera...")

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
                    "Camera Height": camera_height,
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
                    "Camera Height": camera_height,
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
                    "Camera Height": camera_height,
                    "Reason": (
                        "No Takeout video overlapped the requested time"
                    )
                })

                print(
                    f"MISS: {participant_code} {camera_height} "
                    f"{row['Set']} {row['Event']} "
                    f"{clip_start} -> {clip_end}"
                )
                continue

            try:
                output_filename = create_output_filename(
                    set_name=row["Set"],
                    event_name=row["Event"],
                    camera_height=camera_height
                )
            except ValueError as error:
                naming_error_rows.append({
                    **row,
                    "Camera Height": camera_height,
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

            output_path = participant_folder / output_filename

            if args.skip_existing and output_path.exists():
                print(
                    f"SKIP EXISTING: "
                    f"{participant_code}/{output_filename}"
                )
                continue

            # Keep old behavior when --skip-existing is not used.
            if not args.skip_existing:
                output_path = create_unique_output_path(
                    participant_folder,
                    output_filename
                )

            print(
                f"Clipping {participant_code}/{output_path.name} "
                f"from {len(matching_videos)} video file(s)"
            )

            try:
                success = clip_across_videos(
                    matching_videos=matching_videos,
                    output_path=output_path,
                    clip_start=clip_start,
                    clip_end=clip_end
                )
            except (subprocess.CalledProcessError, RuntimeError) as error:
                if output_path.exists():
                    output_path.unlink()

                missed_rows.append({
                    **row,
                    "Camera Height": camera_height,
                    "Reason": f"FFmpeg clipping error: {error}"
                })

                print(
                    f"CLIP ERROR: {participant_code} "
                    f"{camera_height} {row['Set']} {row['Event']} — "
                    f"{error}"
                )
                continue

            if not success:
                if output_path.exists():
                    output_path.unlink()

                missed_rows.append({
                    **row,
                    "Camera Height": camera_height,
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