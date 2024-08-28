# from mms.align_utils import (
#     DEVICE,
#     get_alignments,
#     get_spans,
#     get_uroman_tokens,
#     load_model_dict,
# )
import urllib.request

import sox
from flask import Flask

app = Flask(__name__)


@app.route("/")
def hello_world():
    mp3 = "test.mp3"
    urllib.request.urlretrieve(
        "https://firebasestorage.googleapis.com/v0/b/waha-ai-timestamper-4265a.appspot.com/o/sessions%2F9548f8a3-0e9e-4ff3-a5c7-1889c12e3ba3%2Ftest%20copy%203.wav?alt=media",
        mp3,
    )
    total_duration = sox.file_info.duration(mp3)
    return f"Duration: {total_duration}"
