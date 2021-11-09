import sys
sys.path.append(".")

import torch
import numpy as np

from metrics.image_distance import SSIM, PSNR, MSE, MAE
from metrics.segmentation import Accuracy as ACC
from losses.image_perceptual import LPIPS
from losses.fvd import FrechetVideoDistance as FVD


def get_segmentation_metrics(pred, target):
    '''
    input type: torch.tensor (torch.int)
    input shape: [b, h, w]
    input range: class labels starting from 0
    '''

    pred_stacked = list(pred.detach().cpu())
    target_stacked = list(target.detach().cpu())

    return {
        "accuracy (↑)": np.mean([ACC(p, t) for p, t in zip(pred_stacked, target_stacked)])
    }


def get_prediction_metrics(pred, target, frames=None):
    '''
    input type: torch.tensor (torch.float)
    input shape: [b, t, c, h, w]
    input range: [-1.0, 1.0]
    if frames is specified, only considers the first 'frames' frames.
    '''

    if pred.shape != target.shape:
        raise ValueError("Output images and target images are of different shape!")

    frames = frames or pred.shape[1]
    pred = pred[:, :frames]
    target = target[:, :frames]
    b, t, c, h, w = pred.shape

    # for image-level losses: create zippable lists of pred-target numpy array pairs, removing other dimensions
    pred_stacked = pred.view(-1, *pred.shape[2:]).detach().cpu()
    pred_torch, pred_numpy = list(pred_stacked), list(pred_stacked.numpy())
    target_stacked = target.view(-1, *target.shape[2:]).detach().cpu()
    target_torch, target_numpy = list(target_stacked), list(target_stacked.numpy())

    return {
        f"ssim_{frames} (↑)": np.mean([SSIM(p, t) for p, t in zip(pred_numpy, target_numpy)]),
        f"psnr_{frames} (↑)": np.mean([PSNR(p, t) for p, t in zip(pred_numpy, target_numpy)]),
        f"mse_{frames} (↓)": np.mean([MSE(p, t) for p, t in zip(pred_numpy, target_numpy)]),
        f"mae_{frames} (↓)": np.mean([MAE(p, t) for p, t in zip(pred_numpy, target_numpy)]),
        f"lpips_{frames} (↓)": LPIPS(device=pred.device).forward(pred, target).item(),
        f"fvd_{frames} (↓)": FVD(device=pred.device, num_frames=t, in_channels=c).forward(pred, target).item()
    }


if __name__ == '__main__':
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print("\nPrediction metrics:")
    a, b = torch.rand(8, 16, 3, 93, 124).to(device), torch.rand(8, 16, 3, 93, 124).to(device)  # [b, t, c, h, w]
    a, b = 2*a-1, 2*b-1  # range: [-1.0, 1.0)
    for metric, val in get_prediction_metrics(a, b).items():
        print(f"{metric}: {val}")

    print("\nSegmentation metrics:")
    x, y = torch.rand(8, 93, 124).to(device), torch.rand(8, 93, 124).to(device)  # [b, h, w]
    x, y = (10*x).int(), (10*y).int()
    for metric, val in get_segmentation_metrics(x, y).items():
        print(f"{metric}: {val}")
