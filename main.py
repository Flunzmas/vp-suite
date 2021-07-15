import sys, os, time
from pathlib import Path

import torch
import torch.nn as nn
from tqdm import tqdm
from torch.utils.data import DataLoader

from config import *
from dataset import SynpickDataset, get_training_augmentation, get_validation_augmentation
from models.seg_model import UNet
from utils import CrossEntropyLoss, get_accuracy
from visualize import visualize

def main(args):

    # DATA
    data_dir = args[0]
    train_dir = os.path.join(data_dir, 'train')
    val_dir = os.path.join(data_dir, 'val')
    test_dir = os.path.join(data_dir, 'test')

    train_data = SynpickDataset(data_dir=train_dir, augmentation=get_training_augmentation())
    val_data = SynpickDataset(data_dir=val_dir, augmentation=get_validation_augmentation())

    train_loader = DataLoader(train_data, batch_size=BATCH_SIZE, shuffle=True, num_workers=12)
    valid_loader = DataLoader(val_data, batch_size=1, shuffle=False, num_workers=4)

    # MODEL
    seg_model = UNet(in_channels=3, out_channels=train_data.NUM_CLASSES).to(DEVICE)

    # ETC
    loss_fn = CrossEntropyLoss()
    optimizer = torch.optim.Adam(params=seg_model.parameters(), lr=LEARNING_RATE)

    max_accuracy = 0
    timestamp = int(1000000 * time.time())
    out_dir = Path("out/run_{}".format(timestamp))
    out_dir.mkdir(parents=True)

    # TRAINING
    for i in range(0, NUM_EPOCHS):
        print('\nEpoch: {}'.format(i))

        loop = tqdm(train_loader)
        for batch_idx, (data, targets) in enumerate(loop):
            data = data.to(DEVICE)
            targets = targets.to(DEVICE)

            predictions = seg_model(data)
            loss = loss_fn.get_loss(predictions, targets)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            loop.set_postfix(loss=loss.item())

        print("Validating...")
        accuracy = get_accuracy(valid_loader, seg_model, DEVICE)
        print("Accuracy = {}".format(accuracy))

        # save model if last epoch improved acc.
        if max_accuracy < accuracy:
            max_accuracy = accuracy
            torch.save(seg_model, str((out_dir / 'best_model.pth').resolve()))
            print('Model saved!')

        # visualize model predictions using eval mode and validation data
        visualize(val_data, seg_model)

        if i == 25:
            optimizer.param_groups[0]['lr'] *= 0.1
            print('Decrease decoder learning rate!')

    # TESTING
    print("Training done, testing best model...")
    best_model = torch.load(str((out_dir / 'best_model.pth').resolve()))
    test_data = SynpickDataset(data_dir=test_dir, augmentation=get_validation_augmentation())
    visualize(test_data, best_model)


if __name__ == '__main__':
    main(sys.argv[1:])