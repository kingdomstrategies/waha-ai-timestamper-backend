import os
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
    text_extension = ".txt"

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
        elif ext == text_extension:
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
    session_doc_ref: Any,
    matches: list[tuple[File, File]],
    model: Any,
    dictionary: Any,
):
    """
    Align audio and text files and write output to Firestore.
    """

    file_timestamps: list[FileTimestamps] = []
    folder = f"/tmp/sessions/{session_id}"
    Path(folder).mkdir(parents=True, exist_ok=True)

    for match in matches:
        try:
            audio_output = f"{folder}/{match[0][0]}"
            audio_type = match[0][0].split(".")[-1]

            text_output = f"{folder}/{match[1][0]}"

            audio_spinner = Halo(text=f"Downloading audio to {audio_output}...").start()

            bucket.blob(match[0][2]).download_to_filename(audio_output)

            wav_output = audio_output.replace(f".{audio_type}", ".wav")

            audio_spinner.text = "Converting audio to {wav_output}..."
            stream = ffmpeg.input(audio_output)
            stream = ffmpeg.output(stream, wav_output, acodec="pcm_s16le", ar=16000)
            stream = ffmpeg.overwrite_output(stream)
            ffmpeg.run(
                stream,
                overwrite_output=True,
                cmd=["ffmpeg", "-loglevel", "error"],  # type: ignore
            )
            audio_spinner.succeed(f"Audio downloaded and converted to {wav_output}.")

            text_output = f"{folder}/{match[1][0]}"
            text_spinner = Halo(f"Downloading text to {text_output}...").start()
            bucket.blob(match[1][2]).download_to_filename(text_output)
            text_spinner.succeed(f"Text downloaded to {text_output}.")

            norm_spinner = Halo("Normalizing and romanizing... ").start()
            lines_to_timestamp = (
                open(text_output, "r", encoding="utf-8").read().split("\n")
            )
            norm_lines_to_timestamp = [
                text_normalize(line.strip(), language) for line in lines_to_timestamp
            ]
            uroman_lines_to_timestamp = get_uroman_tokens(
                norm_lines_to_timestamp, language
            )
            uroman_lines_to_timestamp = ["<star>"] + uroman_lines_to_timestamp
            lines_to_timestamp = ["<star>"] + lines_to_timestamp
            norm_lines_to_timestamp = ["<star>"] + norm_lines_to_timestamp
            norm_spinner.succeed("Text normalized and romanized.")

            align_spinner = Halo("Aligning...").start()

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
        except Exception:
            session_doc_ref.set({"status": Status.FAILED.value}, merge=True)
            return

        align_spinner.succeed("Alignment done.")

        clean_spinner = Halo("Cleaning up...").start()
        os.remove(wav_output)
        os.remove(audio_output)
        os.remove(text_output)
        clean_spinner.succeed("Cleaned up.")

        file_timestamps.append(
            {
                "audio_file": match[0][0],
                "text_file": match[1][0],
                "sections": sections,
            }
        )

    doc_spinner = Halo("Uploading to Firestore...").start()
    session_doc_ref.set(
        {"timestamps": file_timestamps, "status": Status.DONE.value}, merge=True
    )
    doc_spinner.succeed("Uploaded to Firestore.")
