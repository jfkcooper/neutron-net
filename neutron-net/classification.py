from comet_ml import Experiment

import os, time, re, glob, warnings
import argparse
import json
import h5py

os.environ["KMP_AFFINITY"] = "none"

import numpy as np 
import pandas as pd 

from datetime import datetime
from sklearn.metrics import mean_squared_error, confusion_matrix

import tensorflow as tf
from tensorflow.keras.models import Sequential, Model
from tensorflow.keras.layers import Dense, Flatten, Conv2D, MaxPooling2D, LeakyReLU, Dropout, Input
from tensorflow.keras.utils import Sequence
from tensorflow.keras.utils import plot_model
from tensorflow.keras.callbacks import ReduceLROnPlateau, EarlyStopping, ModelCheckpoint
from tensorflow.keras.optimizers import Nadam

DIMS = (300, 300)
CHANNELS = 1
tf.compat.v1.disable_eager_execution()

class Sequencer(Sequence):
    """ Use Keras Sequence class to load image data from h5 file"""
    def __init__(self, file, dim, channels, batch_size, debug=False, shuffle=False):
        self.file       = file
        # self.labels     = labels
        self.dim        = dim
        self.channels   = channels
        self.batch_size = batch_size
        self.debug      = debug
        self.shuffle    = shuffle
        self.on_epoch_end()
    
    def __len__(self):
        """ Denotes number of batches per epoch"""
        return int(np.floor(len(self.file["images"]) / self.batch_size))

    def __getitem__(self, idx):
        """ Generates one batch of data"""
        indexes = self.indexes[idx*self.batch_size:(idx+1) * self.batch_size]
        inputs, targets = self.__data_generation(indexes)

        return inputs, targets

    def __data_generation(self, indexes):
        """ Generates data containing batch_size samples"""
        images = np.empty((self.batch_size, *self.dim, self.channels))
        classes = np.empty((self.batch_size, 1), dtype=int)

        for i, idx in enumerate(indexes):
            image = self.file["images"][idx]
            images[i,] = image
            classes[i,] = self.file["layers"][idx]      
        return images, classes
    
    def on_epoch_end(self):
        """Updates indexes after each epoch"""
        indexes = np.arange(0, len(self.file["images"]))

        if self.shuffle:
            np.random.shuffle(indexes)

        self.indexes = indexes

class Classifier():
    def __init__(self, dims, channels, epochs, dropout, lr, workers):
        """ Initialisation"""
        self.dims       = dims
        self.channels   = channels
        self.epochs     = epochs
        self.dropout    = dropout
        self.lr         = lr
        self.workers    = workers
        self.model      = self.create_model()

    def train(self, train_sequence, validate_sequence):
        """ Train and validate network"""
        learning_rate_reduction_cbk = ReduceLROnPlateau(
            monitor="val_loss",
            patience=10,
            verbose=1,
            factor=0.5,
            min_lr=0.000001,
        )

        self.history = self.model.fit(
            train_sequence,
            validation_data=validate_sequence,
            epochs=self.epochs,
            workers=self.workers,
            use_multiprocessing=False,
            verbose=1,
            callbacks=[learning_rate_reduction_cbk],
        )

        return self.history

    def create_model(self):
        model = Sequential()

        model.add(Conv2D(32, (3,3), strides=(1,1), padding='same', activation="relu", input_shape=(*self.dims, self.channels)))
        model.add(MaxPooling2D(pool_size=(2,2)))

        model.add(Conv2D(64, (3,3), strides=(1,1), padding='same', activation="relu"))
        model.add(MaxPooling2D(pool_size=(2,2)))

        model.add(Conv2D(128, (3,3), strides=(1,1), padding='same', activation="relu"))
        model.add(MaxPooling2D(pool_size=(3,3), strides=(2,2)))

        model.add(Conv2D(32, (3,3), strides=(1,1), padding='same', activation="relu"))
        model.add(MaxPooling2D(pool_size=(3,3), strides=(2,2)))

        model.add(Flatten()) # Length: 256 filters x 18 x 18 = 82944
        # model.add(Dense(150, activation="relu"))
        model.add(Dense(300, activation="relu"))
        model.add(Dropout(self.dropout))
        model.add(Dense(240, activation="relu"))
        model.add(Dropout(self.dropout))
        model.add(Dense(192, activation="relu"))
        model.add(Dropout(self.dropout))
        model.add(Dense(154, activation="relu"))
        model.add(Dropout(self.dropout))
        model.add(Dense(123, activation="relu"))
        model.add(Dropout(self.dropout))
        model.add(Dense(98, activation="relu"))
        model.add(Dropout(self.dropout))
        model.add(Dense(79, activation="relu"))
        model.add(Dropout(self.dropout))
        model.add(Dense(63, activation="relu"))
        model.add(Dropout(self.dropout))
        model.add(Dense(50, activation="relu"))
        model.add(Dropout(self.dropout))
        model.add(Dense(3, activation="softmax"))

        model.compile(
            optimizer=Nadam(self.lr),
            loss="sparse_categorical_crossentropy",
            metrics=["sparse_categorical_accuracy"]
        )
        return model
    
    def summary(self):
        self.model.summary()


def main(args):
    name = "classifier-[" + datetime.now().strftime("%Y-%m-%dT%H%M%S") + "]"
    savepath = os.path.join(args.save, name)

    data = r"D:\Users\Public\Documents\stfc\neutron-net\data\single"

    if args.log:
        experiment = Experiment(api_key="Qeixq3cxlTfTRSfJ2hyPlMWjk", project_name="general", workspace="xandrovich")

    train_dir = os.path.join(data, "train.h5")
    validate_dir = os.path.join(data, "validate.h5")
    test_dir = os.path.join(data, "test.h5")

    train_file = h5py.File(train_dir, "r")
    validate_file = h5py.File(validate_dir, "r")
    test_file = h5py.File(test_dir, "r")

    train_loader = Sequencer(train_file, DIMS, CHANNELS, args.batch_size, debug=True, shuffle=True)
    validate_loader = Sequencer(validate_file, DIMS, CHANNELS, args.batch_size, shuffle=False)
    test_loader = Sequencer(test_file, DIMS, CHANNELS, args.batch_size, shuffle=False)

    model = Classifier(DIMS, CHANNELS, args.epochs, args.dropout_rate, args.learning_rate, args.workers)
    model.summary()
    model.train(train_loader, validate_loader)


def parse():
    parser = argparse.ArgumentParser(description="Keras Classifier Training")
    # Meta Parameters
    parser.add_argument("data", metavar="PATH", help="path to data directory")
    parser.add_argument("save", metavar="PATH", help="path to save directory")
    parser.add_argument("-l", "--log", action="store_true", help="boolean: log metrics to CometML?")

    # Model parameters
    parser.add_argument("-e", "--epochs", default=2, type=int, metavar="N", help="number of epochs")
    parser.add_argument("-b", "--batch_size", default=40, type=int, metavar="N", help="no. samples per batch (def:40)")
    parser.add_argument("-j", "--workers", default=1, type=int, metavar="N", help="no. data loading workers (def:1)")
    
    # Learning parameters
    parser.add_argument("-lr", "--learning_rate", default=0.0003, type=float, metavar="R", help="Nadam learning rate")
    parser.add_argument("-dr", "--dropout_rate", default=0.1, type=float, metavar="R", help="dropout rate" )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse()
    main(args)