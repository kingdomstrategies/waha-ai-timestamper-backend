import os
import re
import time
from pathlib import Path
from typing import Any

import ffmpeg
from halo import Halo

from firebase import bucket
from mms.align_utils import get_alignments, get_spans, get_uroman_tokens
from mms.text_normalization import text_normalize
from timestamp_types import File, FileTimestamps, Match, Section, Status


def match_files(
    files: list[File],
) -> list[Match]:
    """
    Match audio and text files by name (without extension).
    """

    audio_extensions = {".wav", ".mp3"}
    text_extensions = {".txt", ".usfm"}

    # Dictionary to store matched files by name (without extension)
    matched_files = {}

    for filename, url, path in files:
        name, ext = filename.rsplit(".", 1)

        ext = f".{ext}"

        if ext in audio_extensions:
            if name not in matched_files:
                matched_files[name] = (None, None)
            matched_files[name] = (
                (filename, url, path),
                matched_files[name][1],
            )  # Store audio file
        elif ext in text_extensions:
            if name not in matched_files:
                matched_files[name] = (None, None)
            matched_files[name] = (
                matched_files[name][0],
                (filename, url, path),
            )  # Store text file

    # Filter out pairs where either the audio or text is missing
    return [match for match in matched_files.values() if None not in match]


def align_matches(
    session_id: str,
    language: str,
    separator: str,
    session_doc_ref: Any,
    matches: list[tuple[File, File]],
    model: Any,
    dictionary: Any,
):
    """
    Align audio and text files and write output to Firestore.
    """
    spinner = Halo("Aligning...").start()

    file_timestamps: list[FileTimestamps] = []
    folder = f"/tmp/sessions/{session_id}"
    Path(folder).mkdir(parents=True, exist_ok=True)

    progress = 0
    session_doc_ref.set({"total": len(matches), "progress": progress}, merge=True)
    total_length = 0

    for match in matches:
        session_doc_ref.set({"current": match[0][0]}, merge=True)
        try:
            audio_output = f"{folder}/{match[0][0]}"
            audio_type = match[0][0].split(".")[-1]

            text_output = f"{folder}/{match[1][0]}"

            spinner.text = f"Downloading audio to {audio_output}..."
            spinner.start()

            bucket.blob(match[0][2]).download_to_filename(audio_output)

            spinner.succeed(f"Audio downloaded to {audio_output}.")

            wav_output = audio_output.replace(f".{audio_type}", "_output.wav")

            spinner.text = f"Converting audio to {wav_output}..."
            spinner.start()

            total_length += float(ffmpeg.probe(audio_output)["streams"][0]["duration"])
            stream = ffmpeg.input(audio_output)
            stream = ffmpeg.output(stream, wav_output, acodec="pcm_s16le", ar=16000)
            stream = ffmpeg.overwrite_output(stream)
            ffmpeg.run(
                stream,
                overwrite_output=True,
                cmd=["ffmpeg", "-loglevel", "error"],  # type: ignore
            )
            spinner.succeed(f"Audio downloaded and converted to {wav_output}.")

            text_output = f"{folder}/{match[1][0]}"
            spinner.text = f"Downloading text to {text_output}..."
            spinner.start()
            bucket.blob(match[1][2]).download_to_filename(text_output)
            spinner.succeed(f"Text downloaded to {text_output}.")

            spinner.text = "Normalizing and romanizing... "
            spinner.start()

            text_extension = match[1][0].split(".")[-1]

            text_file = open(text_output, "r", encoding="utf-8")
            lines_to_timestamp = []

            if text_extension == "txt":
                # Read the separator from the query parameter and adjust
                # it so it can be used in the split function.
                if separator == "lineBreak":
                    separator = "\n"
                elif separator == "squareBracket":
                    separator = "["
                elif separator == "downArrow":
                    separator = "⬇️"

                lines_to_timestamp = text_file.read().split(separator)
            elif text_extension == "usfm":
                # Define the tags to ignore
                ignore_tags = [
                    "\\c",
                    "\\p",
                    "\\s",
                    "\\s1",
                    "\\s2",
                    "\\f",
                    "\\ft",
                    "\\fr",
                    "\\x",
                    "\\xt",
                    "\\xo",
                    "\\r",
                    "\\t",
                    "\\m",
                ]

                # Compile a regex to match tags we want to ignore
                ignore_regex = re.compile(
                    r"|".join(re.escape(tag) for tag in ignore_tags)
                )
                current_verse = ""
                for line in text_file:
                    if ignore_regex.match(line.strip()):
                        continue

                    if line.startswith(r"\v"):  # USFM verse marker
                        if current_verse:
                            cleaned_verse = re.sub(
                                r"\\[a-z]+\s?", "", current_verse.strip()
                            )
                            lines_to_timestamp.append(cleaned_verse)
                        current_verse = line.strip()  # Start a new verse
                    else:
                        current_verse += " " + line.strip()

                if current_verse:  # Append the last verse after the loop
                    cleaned_verse = re.sub(r"\\[a-z]+\s?", "", current_verse.strip())
                    lines_to_timestamp.append(cleaned_verse)

            norm_lines_to_timestamp = [
                text_normalize(line.strip(), language) for line in lines_to_timestamp
            ]
            uroman_lines_to_timestamp = get_uroman_tokens(
                norm_lines_to_timestamp, language
            )
            uroman_lines_to_timestamp = ["<star>"] + uroman_lines_to_timestamp
            lines_to_timestamp = ["<star>"] + lines_to_timestamp
            norm_lines_to_timestamp = ["<star>"] + norm_lines_to_timestamp
            spinner.succeed("Text normalized and romanized.")

            spinner.text = "Aligning..."
            spinner.start()

            segments, stride = get_alignments(
                wav_output,
                uroman_lines_to_timestamp,
                model,
                dictionary,
            )

            spans = get_spans(uroman_lines_to_timestamp, segments)

            sections = []

            for i, t in enumerate(lines_to_timestamp):
                span = spans[i]
                seg_start_idx = span[0].start
                seg_end_idx = span[-1].end

                audio_start_sec = seg_start_idx * stride / 1000
                audio_end_sec = seg_end_idx * stride / 1000

                section: Section = {
                    "begin": audio_start_sec,
                    "end": audio_end_sec,
                    "begin_str": time.strftime(
                        "%H:%M:%S", time.gmtime(audio_start_sec)
                    ),
                    "end_str": time.strftime("%H:%M:%S", time.gmtime(audio_end_sec)),
                    "text": t,
                    "uroman_tokens": uroman_lines_to_timestamp[i],
                }

                sections.append(section)
        except Exception as e:
            spinner.fail("Failed to align.")
            print(e)
            session_doc_ref.set(
                {"status": Status.FAILED.value, "error": str(e)}, merge=True
            )
            return

        spinner.succeed("Alignment done.")

        spinner.text = "Cleaning up..."
        spinner.start()
        os.remove(wav_output)
        os.remove(audio_output)
        os.remove(text_output)
        spinner.succeed("Cleaned up.")

        file_timestamps.append(
            {
                "audio_file": match[0][0],
                "text_file": match[1][0],
                "sections": sections,
            }
        )
        progress += 1
        session_doc_ref.set({"progress": progress}, merge=True)

    doc_spinner = Halo("Uploading to Firestore...").start()
    session_doc_ref.set(
        {
            "timestamps": file_timestamps,
            "status": Status.DONE.value,
            "end": time.time(),
            "total_length": total_length,
        },
        merge=True,
    )
    doc_spinner.succeed("Uploaded to Firestore.")
