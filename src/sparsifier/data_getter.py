import glob
import gzip
import random
from pathlib import Path

import cv2
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pudb
import torch
import torchvision.transforms as transforms
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms as transforms
from torchvision import utils
from torchvision.transforms import ToTensor
from tqdm import tqdm

matplotlib.use("Agg")


def get_dict(fname):
    f = gzip.open(
        "../../data/datasets/pointnav/gibson/v2/train_large/content/"
        + fname
        + ".json.gz"
    )
    content = f.read()
    content = content.decode()
    content = content.replace("null", "None")
    content = eval(content)
    return content["episodes"]


class GibsonDataset(Dataset):
    """ Dataset collect from Habitat """

    def __init__(self, split_type, seed, visualize=False, max_distance=10):
        random.seed(seed)
        self.split_type = split_type
        self.max_distance = max_distance
        # This is changed in the train_large_data.py file
        self.episodes = 100
        self.image_data_path = (
            "../../data/datasets/pointnav/gibson/v2/train_large/images/"
        )
        self.dict_path = "../../data/datasets/pointnav/gibson/v2/train_large/content/"
        self.env_names = self.get_env_names()
        random.shuffle(self.env_names)
        split = 0.85
        self.train_env = self.env_names[0 : int(len(self.env_names) * split)]
        self.test_env = self.env_names[int(len(self.env_names) * split) :]
        if visualize:
            d = get_dict(self.train_env[0])
            self.visualize_dict(d[0])
        if split_type == "train":
            self.dataset = self.get_dataset(self.train_env)
        elif split_type == "test":
            self.dataset = self.get_dataset(self.test_env)
        self.dataset = self.balance_dataset(10000)
        self.dataset = self.flatten_dataset()
        self.verify_dataset()

    def save_env_data(self, path):
        np.save(path + "train_env.npy", self.train_env)
        np.save(path + "test_env.npy", self.test_env)

    # Make sure all of the images exist
    def verify_dataset(self):
        for data in self.dataset:
            env, episode, l1, l2 = data
            img_file1 = Path(
                self.image_data_path
                + env
                + "/"
                + "episode"
                + str(episode)
                + "_"
                + str(l1).zfill(5)
                + ".jpg"
            )
            img_file2 = Path(
                self.image_data_path
                + env
                + "/"
                + "episode"
                + str(episode)
                + "_"
                + str(l2).zfill(5)
                + ".jpg"
            )
            assert img_file1.is_file()
            assert img_file2.is_file()

    def flatten_dataset(self):
        # Dataset comes in as dict, would like it as a huge list of tuples
        ret = []
        for key, value in self.dataset.items():
            ret = ret + value
        random.shuffle(ret)
        return ret

    def balance_dataset(self, max_number_of_examples=2000):
        min_size = np.inf
        for i in range(self.max_distance):
            min_size = min(min_size, len(self.dataset[i]))
        min_size = min(min_size, max_number_of_examples)
        far_away_keys = range(self.max_distance, len(self.dataset) - self.max_distance)
        ret = {}
        far_away_dataset = []
        for i in range(min_size):
            idx = np.random.choice(far_away_keys)
            key = self.max_distance
            if key not in ret:
                ret[key] = []
            ret[key].append(random.choice(self.dataset[idx]))
        for i in range(self.max_distance):
            ret[i] = random.sample(self.dataset[i], min_size)
        return ret

    # Don't forget map/trajectory is directed.
    def get_dataset(self, envs):
        ret = {}
        for env in tqdm(envs):
            # Get step difference between all points to each other
            for episode in range(self.episodes):
                paths = glob.glob(
                    self.image_data_path + env + "/" + "episode" + str(episode) + "_*"
                )
                for i in range(len(paths)):
                    for j in range(i, len(paths)):
                        key = j - i
                        if key > 30:
                            break
                        if key not in ret:
                            ret[key] = []
                        ret[key].append((env, episode, i, j))
        return ret

    def get_env_names(self):
        paths = glob.glob(self.dict_path + "*")
        paths.sort()
        names = [Path(Path(path).stem).stem for path in paths]
        return names

    def visualize_dict(self, d):
        start = d["start_position"]
        goal = d["goals"][0]["position"]
        traj = []
        traj.append(start)
        for pose in d["shortest_paths"][0]:
            traj.append(pose["position"])
        traj.append(goal)
        traj = np.array(traj)
        plt.plot(traj[:, 2], traj[:, 0])
        plt.savefig("./dict_visualization.jpg")

    def __len__(self):
        return len(self.dataset)

    def get_image(self, env, episode, location):
        image = plt.imread(
            self.image_data_path
            + env
            + "/"
            + "episode"
            + str(episode)
            + "_"
            + str(location).zfill(5)
            + ".jpg"
        )
        image = cv2.resize(image, (224, 224)) / 255
        return image

    def __getitem__(self, idx):
        env, episode, l1, l2 = self.dataset[idx]
        image1 = self.get_image(env, episode, l1)
        image2 = self.get_image(env, episode, l2)
        transform = transforms.Compose(
            [
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
                ),
            ]
        )
        image1 = transform(image1)
        image2 = transform(image2)

        x = (image1, image2)
        #        y = min(l2 - l1, self.max_distance)
        key = l2 - l1
        if key <= 4:
            y = 1
        else:
            y = 0
        return (x, y)


if __name__ == "__main__":
    data = GibsonDataset("train")
    f = data[0]