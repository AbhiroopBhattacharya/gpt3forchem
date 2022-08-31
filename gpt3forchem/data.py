# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/00_data.ipynb.

# %% auto 0
__all__ = ['get_polymer_data', 'get_photoswitch_data']

# %% ../notebooks/00_data.ipynb 2
import os

import pandas as pd

_THIS_DIR = os.path.abspath(os.path.dirname(os.path.abspath("")))


# %% ../notebooks/00_data.ipynb 5
def get_polymer_data(
    datadir="../data" # path to folder with data files
):
    return pd.read_csv(os.path.join(datadir, "polymers.csv"))


# %% ../notebooks/00_data.ipynb 9
def get_photoswitch_data(
    datadir="../data" # path to folder with data files
):
    """By default we drop the rows without E isomer pi-pi* transition wavelength."""
    df =  pd.read_csv(os.path.join(datadir, "photoswitches.csv"))
    df.dropna(subset=['E isomer pi-pi* wavelength in nm'], inplace=True)
    df.reset_index(inplace=True)
    return df
