import os
import time
from multiprocessing.dummy import Pool

import torch
from flask import Flask, request
from halo import Halo

from constants import dict_name, dict_url, model_name, model_url
from firebase import bucket, db
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


@app.route("/")
def align_session():
    session_id = request.args.get("session-id")
    separator = request.args.get("separator")

    if session_id is None:
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

    return "Alignment started.", 200
