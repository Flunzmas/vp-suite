import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.transforms.functional as TF

# inspired by https://www.youtube.com/watch?v=IHq1t7NxS8k

class UNet(nn.Module):

    def __init__(self, in_channels=3, out_channels=1, features=[64, 128, 256, 512]):
        super(UNet, self).__init__()
        self.downs = nn.ModuleList()
        self.ups = nn.ModuleList()
        self.pool = nn.MaxPool2d(kernel_size=2, stride=2)

        for feature in features:
            self.downs.append(DoubleConv(in_channels=in_channels, out_channels=feature))
            in_channels = feature

        for feature in reversed(features):
            self.ups.append(nn.ConvTranspose2d(in_channels=feature*2, out_channels=feature, kernel_size=2, stride=2))
            self.ups.append(DoubleConv(in_channels=feature * 2, out_channels=feature))

        self.bottleneck = DoubleConv(in_channels=features[-1], out_channels=features[-1] * 2)
        self.final_conv = nn.Conv2d(in_channels=features[0], out_channels=out_channels, kernel_size=1)


    def forward(self, x):
        skip_connections = []

        # DOWN
        for down in self.downs:
            x = down(x)
            skip_connections.append(x)
            x = self.pool(x)

        # BOTTLENECK
        x = self.bottleneck(x)

        # UP
        skip_connections = skip_connections[::-1]
        for i in range(0, len(self.ups), 2):
            x = self.ups[i](x)
            skip_connection = skip_connections[i//2]

            if x.shape != skip_connection.shape:
                x = TF.resize(x, size=skip_connection.shape[2:])

            concat_skip = torch.cat((skip_connection, x), dim=1)
            x = self.ups[i+1](concat_skip)

        # FINAL
        return self.final_conv(x)

class DoubleConv(nn.Module):
    def __init__(self, in_channels, out_channels):
        super(DoubleConv, self).__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, stride=1, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, stride=1, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.conv(x)

def test():
    x = torch.randn((8, 3, 256, 256))
    model = UNet(in_channels=3, out_channels=21)
    preds = model(x)
    print(x.shape, preds.shape)

if __name__ == '__main__':
    test()