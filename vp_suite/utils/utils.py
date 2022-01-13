import sys
from typing import List
from datetime import datetime
import subprocess
import shlex

from tqdm import tqdm
import torch
import torchvision.transforms as TF
from torch import nn as nn


def most(l: List[bool], factor=0.67):
    '''
    Like List.all(), but not 'all' of them.
    '''
    return sum(l) >= factor * len(l)

def timestamp(program):
    """ Obtains a timestamp of the current system time in a human-readable way """

    timestamp = str(datetime.now()).split(".")[0].replace(" ", "_").replace(":", "-")
    return f"{program}_{timestamp}"

def run_command(command, print_to_console=True):
    process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE, encoding='utf8')
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output and print_to_console:
            print(output.strip())
    rc = process.poll()
    return rc

class TqdmUpTo(tqdm):
    """Alternative Class-based version of the above.
    Provides `update_to(n)` which uses `tqdm.update(delta_n)`.
    Taken from https://gist.github.com/leimao/37ff6e990b3226c2c9670a2cd1e4a6f5,
    Inspired by [twine#242](https://github.com/pypa/twine/pull/242),
    [here](https://github.com/pypa/twine/commit/42e55e06).
    """
    def update_to(self, b=1, bsize=1, tsize=None):
        """
        b  : int, optional
            Number of blocks transferred so far [default: 1].
        bsize  : int, optional
            Size of each block (in tqdm units) [default: 1].
        tsize  : int, optional
            Total size (in tqdm units). If [default: None] remains unchanged.
        """
        if tsize is not None:
            self.total = tsize
        self.update(b * bsize - self.n)  # will also set self.n = b * bsize

def download_from_url(url: str, dst_path : str):
    if sys.version_info[0] == 2:
        from urllib import urlretrieve
    else:
        from urllib.request import urlretrieve
    filename = url.split("/")[-1]
    print(f"Downloading from {url}...")
    with TqdmUpTo(unit='B', unit_scale=True, unit_divisor=1024, miniters=1, desc=filename) as t:
        urlretrieve(url, dst_path, reporthook=t.update_to)

class ScaleToTest(nn.Module):
    def __init__(self, model_value_range, test_value_range):
        super(ScaleToTest, self).__init__()
        self.m_min, self.m_max = model_value_range
        self.t_min, self.t_max = test_value_range

    def forward(self, img : torch.Tensor):
        ''' input: [model_val_min, model_val_max] '''
        img = (img - self.m_min) / (self.m_max - self.m_min)  # [0., 1.]
        img = img * (self.t_max - self.t_min) + self.t_min  # [test_val_min, test_val_max]
        return img


class ScaleToModel(nn.Module):
    def __init__(self, model_value_range, test_value_range):
        super(ScaleToModel, self).__init__()
        self.m_min, self.m_max = model_value_range
        self.t_min, self.t_max = test_value_range

    def forward(self, img: torch.Tensor):
        ''' input: [test_val_min, test_val_max] '''
        img = (img - self.t_min) / (self.t_max - self.t_min)  # [0., 1.]
        img = img * (self.m_max - self.m_min) + self.m_min  # [model_val_min, model_val_max]
        return img

def check_dataset_compatibility(model_config, dataset_config, model):
    assert model_config["img_shape"] == dataset_config["img_shape"], \
        "expected img shape of loaded model and dataset img_shape to be the same"
    if model.can_handle_actions and model_config["action_conditional"]:
        assert model_config["action_size"] == dataset_config["action_size"], \
            "expected action size of loaded model and dataset to be the same"

def check_model_compatibility(model_config, run_config, model, strict_mode=False, model_dir:str=None):
    '''
    Checks consistency of the config of a loaded model with given the run configuration.
    Creates appropriate adapter modules to bridge the differences if possible and not in strict_mode.
    Some differences (e.g. action-conditioning vs. not) cannot be bridged and will lead to failure.
    If strict_mode is active, strict compatibility is enforced (adapters are not allowed)
    '''
    model_preprocessing, model_postprocessing = [], []
    model_origin_str =  "" if model_dir is None else f"(loaded from {model_dir})"

    # value range
    model_value_range = list(model_config["tensor_value_range"])
    test_value_range = list(run_config["tensor_value_range"])
    if model_value_range != test_value_range:
        if strict_mode:
            raise ValueError(f"ERROR: model and run value ranges differ")
        model_preprocessing.append(ScaleToModel(model_value_range, test_value_range))
        model_postprocessing.append(ScaleToTest(model_value_range, test_value_range))

    # action conditioning
    mdl_ac, run_ac = model_config["use_actions"], run_config["use_actions"]
    if model.can_handle_actions:
        if mdl_ac:
            if not run_ac:
                raise ValueError(f"ERROR: Action-conditioned model '{model.desc}' {model_origin_str}"
                                 f"can't be invoked without using actions -> set 'use_actions' to True in test cfg!")
            else:
                assert model_config["action_size"] == run_config["action_size"], \
                    f"ERROR: Action-conditioned model '{model.desc}' {model_origin_str} " \
                    f"was trained with action size {model_config['action_size']}, " \
                    f"which is different from the dataset's action size ({run_config['action_size']})"
        elif run_ac:
            raise ValueError(f"ERROR: Action-conditionable model '{model.desc}' {model_origin_str}"
                             f"was trained without using actions -> set 'use_actions' to False in test cfg!")
    elif run_ac:
        print(f"WARNING: Model '{model.desc}' {model_origin_str} can't handle actions"
              f" -> Testing it without using the actions provided by the dataset")

    # img_shape
    model_c, model_h, model_w = model_config["img_shape"]
    test_c, test_h, test_w = run_config["img_shape"]
    if model_c != test_c:
        raise ValueError(f"ERROR: Test dataset provides {test_c}-channel images but "
                         f"Model '{model.desc}' {model_origin_str} expects {model_c} channels")
    elif model_h != test_h or model_w != test_w:
        if strict_mode:
            raise ValueError(f"ERROR: model and run img sizes differ")
        model_preprocessing.append(TF.Resize((model_h, model_w)))
        model_postprocessing.append(TF.Resize((test_h, test_w)))

    # context frames and pred. horizon
    if run_config["context_frames"] is None:
        run_config["context_frames"] = model_config["context_frames"]
    elif run_config["context_frames"] < model.min_context_frames:
        raise ValueError(f"ERROR: Model '{model.desc}' {model_origin_str} needs at least "
                         f"{model.min_context_frames} context frames as it uses temporal convolution "
                         f"with said number as kernel size")
    if run_config["pred_frames"] is None:
        run_config["pred_frames"] = model_config["pred_frames"]

    # finalize pre-/postprocessing modules
    model_preprocessing = nn.Sequential(*model_preprocessing)
    model_postprocessing = nn.Sequential(*model_postprocessing)
    return model_preprocessing, model_postprocessing
