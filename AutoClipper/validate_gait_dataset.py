#!/usr/bin/env python3

import csv
import json
import subprocess
from pathlib import Path
from collections import defaultdict

FFPROBE = "/Users/cienet/Downloads/ffprobe"

EXPECTED_CLIPS_PER_PARTICIPANT = 144

MIN_DURATION = 34
MAX_DURATION = 40


def probe_video(video):

    cmd = [
        FFPROBE,
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type",
        "-of",
        "json",
        str(video)
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return False, None

    try:
        data = json.loads(result.stdout)
    except:
        return False, None

    has_video = any(
        s.get("codec_type") == "video"
        for s in data.get("streams", [])
    )

    duration = None

    try:
        duration = float(
            data["format"]["duration"]
        )
    except:
        pass

    return has_video, duration


def validate_household(root):

    issues = []

    participant_folders = sorted(
        p for p in root.iterdir()
        if p.is_dir()
    )

    print(
        f"\nFound {len(participant_folders)} participants\n"
    )

    for participant in participant_folders:

        print(
            f"Checking {participant.name}"
        )

        videos = sorted(
            participant.glob("*.mp4")
        )

        #################################################
        # COUNT CHECK
        #################################################

        if len(videos) != EXPECTED_CLIPS_PER_PARTICIPANT:

            issues.append({
                "Participant": participant.name,
                "File": "",
                "Issue":
                    f"Expected "
                    f"{EXPECTED_CLIPS_PER_PARTICIPANT} clips "
                    f"but found {len(videos)}"
            })

        #################################################
        # TAB / MNT PAIR CHECK
        #################################################

        base_names = defaultdict(set)

        for video in videos:

            stem = video.stem

            if stem.endswith("-TAB"):
                base_names[
                    stem[:-4]
                ].add("TAB")

            elif stem.endswith("-MNT"):
                base_names[
                    stem[:-4]
                ].add("MNT")

        for scenario, cameras in base_names.items():

            if cameras != {"TAB", "MNT"}:

                issues.append({
                    "Participant": participant.name,
                    "File": scenario,
                    "Issue":
                        f"Missing camera pair "
                        f"({','.join(sorted(cameras))})"
                })

        #################################################
        # VIDEO VALIDATION
        #################################################

        for video in videos:

            has_video, duration = probe_video(video)

            if not has_video:

                issues.append({
                    "Participant": participant.name,
                    "File": video.name,
                    "Issue":
                        "No video stream"
                })

                continue

            if duration is None:

                issues.append({
                    "Participant": participant.name,
                    "File": video.name,
                    "Issue":
                        "No duration"
                })

                continue

            #################################################
            # DUPLICATED CLIP DETECTION
            #################################################

            if duration > MAX_DURATION:

                issues.append({
                    "Participant": participant.name,
                    "File": video.name,
                    "Issue":
                        f"Duration {duration:.2f}s "
                        "(possible duplicate clip)"
                })

            elif duration < MIN_DURATION:

                issues.append({
                    "Participant": participant.name,
                    "File": video.name,
                    "Issue":
                        f"Duration {duration:.2f}s "
                        "(too short)"
                })

        print(
            f"   {len(videos)} clips"
        )

    return issues


def save_report(
        household_folder,
        issues
):

    report = (
        household_folder
        / "validation_report.csv"
    )

    with open(
        report,
        "w",
        newline="",
        encoding="utf8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=[
                "Participant",
                "File",
                "Issue"
            ]
        )

        writer.writeheader()

        for row in issues:
            writer.writerow(row)

    print(
        f"\nSaved report:\n{report}"
    )


if __name__ == "__main__":

    household = Path(
        input(
            "Household folder: "
        ).strip()
    )

    issues = validate_household(
        household
    )

    print(
        f"\nTotal issues: {len(issues)}"
    )

    save_report(
        household,
        issues
    )

    if len(issues) == 0:

        print(
            "\nVALIDATION PASSED"
        )

    else:

        print(
            "\nVALIDATION FAILED"
        )