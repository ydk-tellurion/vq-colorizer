import cv2
import torch
import torch.nn.functional as F
import torchvision.transforms as transforms
import PIL.Image as Image
import numpy as np
import matplotlib.pyplot as plt

from ldm.modules.encoders.modules import OpenCLIP, OPENAI_MEAN, OPENAI_STD


white_line = (255, 255, 255)
black_line = (0, 0, 0)
import os
os.environ["KMP_DUPLICATE_LIB_OK"]="TRUE"
def gap(x: torch.Tensor = None, keepdim=True):
    if len(x.shape) == 4:
        return torch.mean(x, dim=[2, 3], keepdim=keepdim)
    elif len(x.shape) == 3 or len(x.shape) == 2:
        return torch.mean(x, dim=[1], keepdim=keepdim)
    else:
        raise NotImplementedError('gap input should be 3d or 4d tensors')

def maxmin(x):
    maxm = x.max(dim=1, keepdim=True).values
    minm = x.min(dim=1, keepdim=True).values
    x = (x - minm) / (maxm - minm)
    return x

def compute_pwm(s: torch.Tensor, threshold=0.5):
    """
        The shape of input scales tensor should be (b, n, 1)
    """
    n = s.shape[1]
    maxm = s.max(dim=1, keepdim=True).values
    minm = s.min(dim=1, keepdim=True).values
    d = maxm - minm

    # dscale_sum = dscale * n
    return torch.where((s-minm) / d < threshold, torch.ones_like(s) * -1, torch.ones_like(s))
    # return torch.where(s < 0, torch.ones_like(s) * -1, torch.ones_like(s))
    # negative_num = count.sum(dim=[1], keepdim=True)
    # dscale_sum = dscale_sum + dscale * negative_num
    # dscale_pos = dscale_sum / (n - negative_num)
    # return torch.where((s-minm)/d < threshold, -dscale, dscale_pos)

def normalize(path):
    img = Image.open(path).convert('RGB')
    img = transforms.Resize((224, 224))(img)
    img = transforms.ToTensor()(img)
    x = transforms.Normalize(OPENAI_MEAN, OPENAI_STD)(img).unsqueeze(0)
    return x

def show_heatmap(img, scale, height, width, length=16):
    heatmap = cv2.applyColorMap(scale, cv2.COLORMAP_JET)
    result = cv2.addWeighted(img, 0.3, heatmap, 0.7, 0)
    hu = height // length
    wu = width // length
    for i in range(16):
        result[i * hu, :] = black_line
    for i in range(16):
        result[:, i * wu] = black_line
    cv2.namedWindow("heatmap", cv2.WINDOW_NORMAL)
    cv2.imshow("heatmap", result)
    cv2.waitKey()

def interpolate(scale: torch.Tensor, height, width, use_maxmin=True):
    if use_maxmin:
        for i, t in enumerate(scale.view(1, 16, 16).round(decimals=2)[0]):
            print(i, t)
        # scale = compute_pwm(scale, threshold=0.55)
        # scale = maxmin(scale)
        # scale = scale.view(1, height*width, 1)
    scale = scale.permute(0, 2, 1).view(1, 1, 16, 16)
    scale = torch.nn.functional.interpolate\
        (scale, size=(height, width), mode="bicubic").squeeze(0).view(1, height * width)
    scale = compute_pwm(scale, threshold=0.6)
    scale = scale.view(1, height, width).permute(1, 2, 0).cpu().numpy()
    scale = (scale * 255.).astype(np.uint8)
    return scale

if __name__ == '__main__':
    path = "H:/networks/pl-models/miniset/mapping/reference/1.jpg"
    # path1 = "H:/networks/pl-models/miniset/origin/70633521.jpg"
    # path2 = "H:/networks/pl-models/miniset/origin/83162727.jpg"
    # path1 = "H:/networks/pl-models/generated/6.png"
    # path2 = "H:/networks/pl-models/generated/7.png"
    # path3 = "H:/networks/pl-models/generated/2.png"
    # path4 = "H:/networks/pl-models/generated/3.png"
    text = ["ground", "the girl's hair"]
    x = torch.cat([normalize(path)]
                   # normalize(path2),]
    #                normalize(path4)]
                  , 0)
    # x = normalize(path)

    img = cv2.imread(path)
    height, width = img.shape[:2]

    clip = OpenCLIP(type="full").cuda()
    # clip = OpenCLIP(arch="ViT-bigG-14", type="full", device="cpu")

    v = clip.encode(x)
    t = clip.encode_text(text)
    c = t[1].unsqueeze(0)
    t = t[0].unsqueeze(0)

    cls_token = v[:, 0].unsqueeze(1)
    v = v[:, 1:]
    scale = clip.calculate_scale(v, t)
    gscale = clip.calculate_scale(cls_token, t)

    # dscale = scale[0] - scale[1]
    # plt.hist(dscale.cpu().numpy())
    # plt.show()
    dscale = scale[0]
    dscale = dscale.unsqueeze(0)

    # print(gscale[0] - gscale[1])
    scale = interpolate(dscale, height, width)
    result = show_heatmap(img, scale, height, width)