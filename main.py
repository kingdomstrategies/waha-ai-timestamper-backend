import os
import time
from multiprocessing.dummy import Pool
from pathlib import Path

import ffmpeg
import flask
import torch
from flask import Flask, request
from halo import Halo

from constants import dict_name, dict_url, model_name, model_url
from firebase import bucket, db
from lid import identify_language
from mms.align_utils import DEVICE, get_model_and_dict
from timestamp_types import File, Status
from utils import align_matches, match_files

pool = Pool(10)
app = Flask(__name__)

model_spinner = Halo(text="Downloading model...").start()
if os.path.exists(model_name):
    model_spinner.info("Model already downloaded.")
else:
    torch.hub.download_url_to_file(
        model_url,
        model_name,
    )
    model_spinner.succeed("Model downloaded.")
assert os.path.exists(model_name)

dict_spinner = Halo(text="Downloading dictionary...").start()
if os.path.exists(dict_name):
    dict_spinner.info("Dictionary already downloaded.")
else:
    torch.hub.download_url_to_file(
        dict_url,
        dict_name,
    )
    dict_spinner.succeed("Dictionary downloaded.")
assert os.path.exists(dict_name)

load_spinner = Halo(text="Loading model and dictionary...").start()
model, dictionary = get_model_and_dict()
dictionary["<star>"] = len(dictionary)
model = model.to(DEVICE)
load_spinner.succeed("Model and dictionary loaded. Ready to receive requests.")


@app.route("/lid")
def lid():
    session_id = request.args.get("session-id")
    file_name = request.args.get("file-name")

    if session_id is None:
        return "Missing session-id parameter", 400
    elif file_name is None:
        return "Missing file-name parameter", 400
    folder = f"/tmp/sessions/{session_id}"
    Path(folder).mkdir(parents=True, exist_ok=True)
    audio_output = f"{folder}/{file_name}"
    audio_type = file_name.split(".")[-1]

    spinner = Halo(text="Downloading audio file...").start()
    try:
        bucket.blob(f"sessions/{session_id}/{file_name}").download_to_filename(
            audio_output
        )
        spinner.succeed("Audio file downloaded.")
    except Exception as e:
        spinner.fail(f"Error downloading audio file: {e}")
        return "Error downloading audio file.", 500

    spinner.text = "Converting audio file to WAV and trimming..."
    spinner.start()

    try:
        wav_output = audio_output.replace(f".{audio_type}", "_output.wav")
        stream = ffmpeg.input(audio_output)
        stream = ffmpeg.output(stream, wav_output, acodec="pcm_s16le", ar=16000, t=30)
        stream = ffmpeg.overwrite_output(stream)
        ffmpeg.run(
            stream,
            overwrite_output=True,
            cmd=["ffmpeg", "-loglevel", "error"],  # type: ignore
        )
        spinner.succeed("Audio file converted to WAV and trimmed.")
    except Exception as e:
        spinner.fail(f"Error converting audio file: {e}")
        return "Error converting audio file.", 500

    spinner.text = "Identifying language..."
    spinner.start()

    try:
        language = identify_language(wav_output)
        spinner.succeed(f"Language identified: {language}")
    except Exception as e:
        spinner.fail(f"Error identifying language: {e}")
        return "Error identifying language.", 500

    response = flask.jsonify({"language": language})
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


@app.route("/")
def align_session():
    session_id = request.args.get("session-id")
    separator = request.args.get("separator")
    language = request.args.get("lang")

    if language is None:
        return "Missing lang parameter", 400
    elif session_id is None:
        return "Missing session-id parameter", 400
    elif separator is None:
        return "Missing separator parameter", 400

    blobs = bucket.list_blobs(prefix=f"sessions/{session_id}")
    files: list[File] = []

    for blob in blobs:
        files.append((blob.name.split("/")[-1], blob.public_url, blob.name))

    if len(files) == 0:
        return "No files found in session", 404

    session_doc_ref = db.collection("sessions").document(session_id)
    session_doc = session_doc_ref.get()
    session_doc = None if not session_doc.exists else session_doc.to_dict()

    if (
        session_doc is not None
        and session_doc.get("status") == Status.IN_PROGRESS.value
    ):
        return "Session already in progress", 400

    matched_files = match_files(files)

    session_doc_ref.set(
        {
            "status": Status.IN_PROGRESS.value,
            "start": time.time(),
            # Overwrite the previous values in case we are restarting a
            # previous alignment.
            "end": None,
            "total": None,
            "progress": None,
            "error": None,
        },
        merge=True,
    )

    # Start alignment in a separate process to avoid blocking the main
    # thread and to send a response to the client immediately.
    pool.apply_async(
        align_matches,
        [
            session_id,
            language,
            separator,
            session_doc_ref,
            matched_files,
            model,
            dictionary,
        ],
    )
    # align_matches(
    #     session_id, language, session_doc_ref, matched_files, model, dictionary
    # )
    response = flask.jsonify({"message": "Alignment started."})
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response
