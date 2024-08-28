import os

import torch

model_name = "ctc_alignment_mling_uroman_model.pt"
model_url = (
    "https://dl.fbaipublicfiles.com/mms/torchaudio/ctc_alignment_mling_uroman/model.pt"
)
dict_name = "ctc_alignment_mling_uroman_model.dict"
dict_url = "https://dl.fbaipublicfiles.com/mms/torchaudio/ctc_alignment_mling_uroman/dictionary.txt"

print("Downloading model...")
if os.path.exists(model_name):
    print("Already downloaded.")
else:
    torch.hub.download_url_to_file(
        model_url,
        model_name,
    )
assert os.path.exists(model_name)
print("Model downloaded.")

print("Downloading dictionary...")
if os.path.exists(dict_name):
    print("Already downloaded.")
else:
    torch.hub.download_url_to_file(
        dict_url,
        dict_name,
    )
print("Dictionary downloaded.")
