import os

import torch

from constants import dict_name, dict_url, model_name, model_url

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
