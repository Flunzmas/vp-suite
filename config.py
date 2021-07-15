import torch

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
BATCH_SIZE = 16
IMG_SIZE = (256, 256)
LEARNING_RATE = 1e-4
NUM_EPOCHS = 20
LOAD_MODEL = False
