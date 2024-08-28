import time
import urllib.request

from flask import Flask

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
    # TODO: The following should be passed in the request.
    wav_url = (
        "https://firebasestorage.googleapis.com/v0/b/waha-ai-timestamper-4265a.appspot.com/"
        "o/sessions%2F1fdbc3e9-6aab-4beb-9277-c0e1390ae345%2Ftest%20copy.wav?alt=media"
    )
    txt_url = (
        "https://firebasestorage.googleapis.com/v0/b/waha-ai-timestamper-4265a.appspot.com/"
        "o/sessions%2F1fdbc3e9-6aab-4beb-9277-c0e1390ae345%2Ftest%20copy.txt?alt=media"
    )
    language = "eng"

    wav_file = "test.wav"
    txt_file = "test.txt"

    urllib.request.urlretrieve(
        wav_url,
        wav_file,
    )
    urllib.request.urlretrieve(
        txt_url,
        txt_file,
    )
    lines_to_timestamp = open(txt_file, "r").read().split("\n")
    norm_lines_to_timestamp = [
        text_normalize(line.strip(), language) for line in lines_to_timestamp
    ]
    uroman_lines_to_timestamp = get_uroman_tokens(norm_lines_to_timestamp, language)

    model, dictionary = get_model_and_dict()
    model = model.to(DEVICE)

    segments, stride = get_alignments(
        wav_file,
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
