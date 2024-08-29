import os
import time
import urllib.parse
import urllib.request

from flask import Flask, request

from mms.align_utils import (
    DEVICE,
    get_alignments,
    get_model_and_dict,
    get_spans,
    get_uroman_tokens,
)
from mms.text_normalization import text_normalize

app = Flask(__name__)


@app.route("/")
def hello_world():
    language = request.args.get("lang")
    audio_file = request.args.get("audio-file")
    text_file = request.args.get("text-file")
    session_id = request.args.get("session-id")

    if audio_file is None:
        return "Missing audio-file parameter", 400
    elif text_file is None:
        return "Missing text-file parameter", 400
    elif language is None:
        return "Missing lang parameter", 400
    elif session_id is None:
        return "Missing session-id parameter", 400

    base_url = "https://firebasestorage.googleapis.com/v0/b/waha-ai-timestamper-4265a.appspot.com/o/"
    audio_path = f"sessions/{session_id}/{audio_file}"
    text_path = f"sessions/{session_id}/{text_file}"
    audio_path_encoded = urllib.parse.quote(audio_path, safe="")
    text_path_encoded = urllib.parse.quote(text_path, safe="")
    audio_url = f"{base_url}{audio_path_encoded}?alt=media"
    text_url = f"{base_url}{text_path_encoded}?alt=media"
    print(audio_url, text_url)

    if not os.path.exists(audio_file):
        print("Downloading audio... ")
        urllib.request.urlretrieve(
            audio_url,
            audio_file,
        )

    if not os.path.exists(text_file):
        print("Downloading text... ")
        urllib.request.urlretrieve(
            text_url,
            text_file,
        )

    print("Normalizing and romanizing... ")
    lines_to_timestamp = open(text_file, "r", encoding="utf-8").read().split("\n")
    norm_lines_to_timestamp = [
        text_normalize(line.strip(), language) for line in lines_to_timestamp
    ]
    uroman_lines_to_timestamp = get_uroman_tokens(norm_lines_to_timestamp, language)

    print("Loading model.... ")
    model, dictionary = get_model_and_dict()
    model = model.to(DEVICE)

    print("Aligning...")
    segments, stride = get_alignments(
        audio_file,
        uroman_lines_to_timestamp,
        model,
        dictionary,
        False,
    )
    spans = get_spans(uroman_lines_to_timestamp, segments)

    sections = []

    for i, t in enumerate(lines_to_timestamp):
        span = spans[i]
        seg_start_idx = span[0].start
        seg_end_idx = span[-1].end

        audio_start_sec = seg_start_idx * stride / 1000
        audio_end_sec = seg_end_idx * stride / 1000

        sample = {
            "begin": audio_start_sec,
            "end": audio_end_sec,
            "begin_str": time.strftime("%H:%M:%S", time.gmtime(audio_start_sec)),
            "end_str": time.strftime("%H:%M:%S", time.gmtime(audio_end_sec)),
            "text": t,
            "uroman_tokens": uroman_lines_to_timestamp[i],
        }

        sections.append(sample)

    return sections
