# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/04_output.ipynb.

# %% auto 0
__all__ = ['aggregate_array', 'string_distances', 'is_valid_smiles', 'is_string_in_training_data', 'get_similarity_to_train_mols',
           'extract_numeric_prediction', 'get_continuos_binned_distance', 'convert2smiles', 'get_num_monomer',
           'get_prompt_compostion', 'get_target', 'get_polymer_prompt_data', 'get_polymer_completion_composition',
           'featurize_many_polymers', 'LinearPolymerSmilesFeaturizer', 'polymer_string2performance',
           'composition_mismatch', 'get_inverse_polymer_metrics', 'get_regression_metrics', 'predict_photoswitch',
           'get_expected_wavelengths', 'test_inverse_photoswitch']

# %% ../notebooks/04_output.ipynb 1
import math
import re
from collections import Counter, defaultdict
from typing import Iterable, List, Optional, Tuple
import os
import joblib
import numpy as np
import pandas as pd
from nbdev.showdoc import *
from rdkit import Chem, DataStructs
from rdkit.Chem.Fingerprints import FingerprintMols
from sklearn.metrics import (max_error, mean_absolute_error,
                             mean_squared_error, r2_score)
from strsimpy.levenshtein import Levenshtein
from strsimpy.longest_common_subsequence import LongestCommonSubsequence
from strsimpy.normalized_levenshtein import NormalizedLevenshtein

from .api_wrappers import extract_inverse_prediction, query_gpt3
from .baselines import compute_fragprints
from .data import POLYMER_FEATURES

# %% ../notebooks/04_output.ipynb 4
_DEFAULT_AGGREGATIONS =  [
        ("min", lambda x: np.min(x)),
        ("max", lambda x: np.max(x)),
        ("mean", lambda x: np.mean(x)),
        ("std", lambda x: np.std(x)),
    ]

def aggregate_array(array, aggregations: Optional[List[Tuple[str, callable]]]= None): 
    if aggregations is None:
        aggregations = _DEFAULT_AGGREGATIONS

    aggregated_array = {}
    for k,v in aggregations:
        aggregated_array[k] = v(array)
    return aggregated_array

# %% ../notebooks/04_output.ipynb 8
def string_distances(
    training_set: Iterable[str], # string representations of the compounds in the training set
    query_string: str # string representation of the compound to be queried
):

    distances = defaultdict(list)

    metrics = [
        ("Levenshtein", Levenshtein()),
        ("NormalizedLevenshtein", NormalizedLevenshtein()),
        ("LongestCommonSubsequence", LongestCommonSubsequence()),
    ]

    aggregations = [
        ("min", lambda x: np.min(x)),
        ("max", lambda x: np.max(x)),
        ("mean", lambda x: np.mean(x)),
        ("std", lambda x: np.std(x)),
    ]

    for training_string in training_set:
        for metric_name, metric in metrics:
            distances[metric_name].append(
                metric.distance(training_string, query_string)
            )

    aggregated_distances = {}

    for k, v in distances.items():
        for agg_name, agg_func in aggregations:
            aggregated_distances[f"{k}_{agg_name}"] = agg_func(v)

    return aggregated_distances


# %% ../notebooks/04_output.ipynb 10
def is_valid_smiles(smiles: str) -> bool:
    """We say a SMILES is valid if RDKit can parse it."""
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return False
        return True
    except:
        return False

# %% ../notebooks/04_output.ipynb 13
def is_string_in_training_data(string: str, training_data: Iterable[str]) -> bool:
    """Check if a string is in the training data.
    
    Note that this is not an exact check of a molecule is in the training data 
    as the model might in principle generate an equivalent, non-canonical SMILES.
    However, one might expect that if a model remembers the training data
    it will simple remember the canonical SMILES.
    """
    return string in training_data

# %% ../notebooks/04_output.ipynb 16
def get_similarity_to_train_mols(smiles: str, train_smiles: List[str]) -> List[float]: 
    train_mols = [Chem.MolFromSmiles(x) for x in train_smiles]
    mol = Chem.MolFromSmiles(smiles)

    train_fps = [Chem.RDKFingerprint(x) for x in train_mols]
    fp = Chem.RDKFingerprint(mol)

    s = DataStructs.BulkTanimotoSimilarity(fp, train_fps)
    return s


# %% ../notebooks/04_output.ipynb 19
def extract_numeric_prediction(predictions: List[str], is_int: bool = True):
    converter = int if is_int else float
    converted = []
    for p in predictions:
        try:
            converted.append(converter(p))
        except:
            converted.append(np.nan)
    return converted

# %% ../notebooks/04_output.ipynb 21
def get_continuos_binned_distance(prediction, bin, bins):
    in_bin = (prediction >= bins[bin][0]) & (prediction < bins[bin][1])
    if in_bin:
        loss = 0
    else:
        # compute the minimum distance to bin
        left_edge_distance = abs(prediction - bins[bin][0])
        right_edge_distance = abs(prediction - bins[bin][1])
        loss = min(left_edge_distance, right_edge_distance)
    return loss


# %% ../notebooks/04_output.ipynb 23
def convert2smiles(string):
    new_encoding = {"A": "[Ta]", "B": "[Tr]", "W": "[W]", "R": "[R]"}

    for k, v in new_encoding.items():
        string = string.replace(k, v)

    string = string.replace("-", "")

    return string


# %% ../notebooks/04_output.ipynb 27
def get_num_monomer(string, monomer):
    num = re.findall(f"([\d+]) {monomer}", string)
    try:
        num = int(num[0])
    except Exception:
        num = 0
    return num


# %% ../notebooks/04_output.ipynb 29
def get_prompt_compostion(prompt):
    composition = {}

    for monomer in ["R", "W", "A", "B"]:
        composition[monomer] = get_num_monomer(prompt, monomer)

    return composition


# %% ../notebooks/04_output.ipynb 30
def get_target(string, target_name="adsorption"):
    num = re.findall(f"([\d+]) {target_name}", string)
    return int(num[0])


# %% ../notebooks/04_output.ipynb 31
def get_polymer_prompt_data(prompt):
    composition = get_prompt_compostion(prompt)

    return composition, get_target(prompt)


# %% ../notebooks/04_output.ipynb 33
def get_polymer_completion_composition(string):
    parts = string.split("-")
    counts = Counter(parts)
    return dict(counts)


# %% ../notebooks/04_output.ipynb 37
# Copyright 2020 PyPAL authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Turn a Polymer SMILES into features"""


def featurize_many_polymers(smiless: list) -> pd.DataFrame:
    """Utility function that runs featurizaton on a
    list of linear polymer smiles and returns a dataframe"""
    features = []
    for smiles in smiless:
        pmsf = LinearPolymerSmilesFeaturizer(smiles)
        features.append(pmsf.featurize())
    return pd.DataFrame(features)


class LinearPolymerSmilesFeaturizer:
    """Compute features for linear polymers"""

    def __init__(self, smiles: str, normalized_cluster_stats: bool = True):
        self.smiles = smiles
        assert "(" not in smiles, "This featurizer does not work for branched polymers"
        self.characters = ["[W]", "[Tr]", "[Ta]", "[R]"]
        self.replacement_dict = dict(
            list(zip(self.characters, ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]))
        )
        self.normalized_cluster_stats = normalized_cluster_stats
        self.surface_interactions = {"[W]": 30, "[Ta]": 20, "[Tr]": 30, "[R]": 20}
        self.solvent_interactions = {"[W]": 30, "[Ta]": 25, "[Tr]": 35, "[R]": 30}
        self._character_count = None
        self._balance = None
        self._relative_shannon = None
        self._cluster_stats = None
        self._head_tail_feat = None
        self.features = None

    @staticmethod
    def get_head_tail_features(string: str, characters: list) -> dict:
        """0/1/2 encoded feature indicating if the building block is at start/end of the polymer chain"""
        is_head_tail = [0] * len(characters)

        for i, char in enumerate(characters):
            if string.startswith(char):
                is_head_tail[i] += 1
            if string.endswith(char):
                is_head_tail[i] += 1

        new_keys = ["head_tail_" + char for char in characters]
        return dict(list(zip(new_keys, is_head_tail)))

    @staticmethod
    def get_cluster_stats(
        s: str, replacement_dict: dict, normalized: bool = True
    ) -> dict:  # pylint:disable=invalid-name
        """Statistics describing clusters such as [Tr][Tr][Tr]"""
        clusters = LinearPolymerSmilesFeaturizer.find_clusters(s, replacement_dict)
        cluster_stats = {}
        cluster_stats["total_clusters"] = 0
        for key, value in clusters.items():
            if value:
                cluster_stats["num" + "_" + key] = len(value)
                cluster_stats["total_clusters"] += len(value)
                cluster_stats["max" + "_" + key] = max(value)
                cluster_stats["min" + "_" + key] = min(value)
                cluster_stats["mean" + "_" + key] = np.mean(value)
            else:
                cluster_stats["num" + "_" + key] = 0
                cluster_stats["max" + "_" + key] = 0
                cluster_stats["min" + "_" + key] = 0
                cluster_stats["mean" + "_" + key] = 0

        if normalized:
            for key, value in cluster_stats.items():
                if "num" in key:
                    try:
                        cluster_stats[key] = value / cluster_stats["total_clusters"]
                    except ZeroDivisionError:
                        cluster_stats[key] = 0

        return cluster_stats

    @staticmethod
    def find_clusters(s: str, replacement_dict: dict) -> dict:  # pylint:disable=invalid-name
        """Use regex to find clusters"""
        clusters = re.findall(
            r"((\w)\2{1,})", LinearPolymerSmilesFeaturizer._multiple_replace(s, replacement_dict)
        )
        cluster_dict = dict(
            list(zip(replacement_dict.keys(), [[] for i in replacement_dict.keys()]))
        )
        inv_replacement_dict = {v: k for k, v in replacement_dict.items()}
        for cluster, character in clusters:
            cluster_dict[inv_replacement_dict[character]].append(len(cluster))

        return cluster_dict

    @staticmethod
    def _multiple_replace(s: str, replacement_dict: dict) -> str:  # pylint:disable=invalid-name
        for word in replacement_dict:
            s = s.replace(word, replacement_dict[word])
        return s

    @staticmethod
    def get_counts(smiles: str, characters: list) -> dict:
        """Count characters in SMILES string"""
        counts = [smiles.count(char) for char in characters]
        return dict(list(zip(characters, counts)))

    @staticmethod
    def get_relative_shannon(character_count: dict) -> float:
        """Shannon entropy of string relative to maximum entropy of a string of the same length"""
        counts = [c for c in character_count.values() if c > 0]
        length = sum(counts)
        probs = [count / length for count in counts]
        ideal_entropy = LinearPolymerSmilesFeaturizer._entropy_max(length)
        entropy = -sum([p * math.log(p) / math.log(2.0) for p in probs])

        return entropy / ideal_entropy

    @staticmethod
    def _entropy_max(length: int) -> float:
        "Calculates the max Shannon entropy of a string with given length"

        prob = 1.0 / length

        return -1.0 * length * prob * math.log(prob) / math.log(2.0)

    @staticmethod
    def get_balance(character_count: dict) -> dict:
        """Frequencies of characters"""
        counts = list(character_count.values())
        length = sum(counts)
        frequencies = [c / length for c in counts]
        return dict(list(zip(character_count.keys(), frequencies)))

    def _featurize(self):
        """Run all available featurization methods"""
        self._character_count = LinearPolymerSmilesFeaturizer.get_counts(
            self.smiles, self.characters
        )
        self._balance = LinearPolymerSmilesFeaturizer.get_balance(self._character_count)
        self._relative_shannon = LinearPolymerSmilesFeaturizer.get_relative_shannon(
            self._character_count
        )
        self._cluster_stats = LinearPolymerSmilesFeaturizer.get_cluster_stats(
            self.smiles, self.replacement_dict, self.normalized_cluster_stats
        )
        self._head_tail_feat = LinearPolymerSmilesFeaturizer.get_head_tail_features(
            self.smiles, self.characters
        )

        self.features = self._head_tail_feat
        self.features.update(self._cluster_stats)
        self.features.update(self._balance)
        self.features["rel_shannon"] = self._relative_shannon
        self.features["length"] = sum(self._character_count.values())
        solvent_interactions = sum(
            [
                [self.solvent_interactions[char]] * count
                for char, count in self._character_count.items()
            ],
            [],
        )
        self.features["total_solvent"] = sum(solvent_interactions)
        self.features["std_solvent"] = np.std(solvent_interactions)
        surface_interactions = sum(
            [
                [self.surface_interactions[char]] * count
                for char, count in self._character_count.items()
            ],
            [],
        )
        self.features["total_surface"] = sum(surface_interactions)
        self.features["std_surface"] = np.std(surface_interactions)

    def featurize(self) -> dict:
        """Run featurization"""
        self._featurize()
        return self.features


# %% ../notebooks/04_output.ipynb 39
def polymer_string2performance(string, model_dir = '../models'):
    # we need to perform a bunch of tasks here:
    # 1) Featurize
    # 2) Query the model

    DELTA_G_MODEL = joblib.load(os.path.join(model_dir, 'delta_g_model.joblib'))

    predicted_monomer_sequence = string.split("@")[0].strip()
    monomer_sq = re.findall("[(R|W|A|B)\-(R|W|A|B)]+", predicted_monomer_sequence)[0]
    composition = get_polymer_completion_composition(monomer_sq)
    smiles = convert2smiles(predicted_monomer_sequence)

    features = pd.DataFrame(featurize_many_polymers([smiles]))
    prediction = DELTA_G_MODEL.predict(features[POLYMER_FEATURES])
    return {
        "monomer_squence": monomer_sq,
        "composition": composition,
        "smiles": smiles,
        "prediction": prediction,
    }


# %% ../notebooks/04_output.ipynb 41
def composition_mismatch(composition: dict, found: dict):
    distances = []

    # We also might have the case the there are keys that the input did not contain
    all_keys = set(composition.keys()) & set(found.keys())

    expected_len = []
    found_len = []

    for key in all_keys:
        try:
            expected = composition[key]
        except KeyError:
            expected = 0
        expected_len.append(expected)
        try:
            f = found[key]
        except KeyError:
            f = 0
        found_len.append(f)

        distances.append(np.abs(expected - f))

    expected_len = sum(expected_len)
    found_len = sum(found_len)
    return {
        "distances": distances,
        "min": np.min(distances),
        "max": np.max(distances),
        "mean": np.mean(distances),
        "expected_len": expected_len,
        "found_len": found_len,
    }


# %% ../notebooks/04_output.ipynb 42
def get_inverse_polymer_metrics(completion_texts, df_test, df_train, max_num_train_sequences = 2000):
    losses = []
    composition_mismatches = []

    train_sequences = [polymer_string2performance(seq)["monomer_squence"] for seq in df_train["completion"]]

    for i, row in tqdm(df_test.iterrows(), total=len(completion_texts)):
        if i < len(completion_texts):
            try:
                composition, bin = get_polymer_prompt_data(row["prompt"])
                completion_data = polymer_string2performance(completion_texts[i])
                loss = get_continuos_binned_distance(completion_data["prediction"][0], bin, bins)
                losses.append(loss)

                mm = composition_mismatch(composition, completion_data["composition"])
                distances = string_distances(
                    train_sequences[:max_num_train_sequences], completion_data["monomer_squence"]
                )
                mm.update(completion_data)
                mm.update(distances)
                mm.update({"loss": loss})
                composition_mismatches.append(mm)
            except Exception as e:
                print(e)
    return losses, pd.DataFrame(composition_mismatches)


# %% ../notebooks/04_output.ipynb 43
def get_regression_metrics(
    y_true,  # actual values (ArrayLike)
    y_pred,  # predicted values (ArrayLike)
) -> dict:

    try:
        return {
            "r2": r2_score(y_true, y_pred),
            "max_error": max_error(y_true, y_pred),
            "mean_absolute_error": mean_absolute_error(y_true, y_pred),
            "mean_squared_error": mean_squared_error(y_true, y_pred),
        }
    except Exception:
        return {
            "r2": np.nan,
            "max_error": np.nan,
            "mean_absolute_error": np.nan,
            "mean_squared_error": np.nan,
        }


# %% ../notebooks/04_output.ipynb 48
def _predict_photoswitch(smiles_string: str,pi_pi_star_model_file='../models/pi_pi_star_model.joblib', n_pi_star_model_file='../models/n_pi_star_model.joblib'):
    """Predicting for a single SMILES string. Not really efficient due to the I/O overhead in loading the model."""
    pi_pi_star_model = joblib.load(pi_pi_star_model_file)
    n_pi_star_model = joblib.load(n_pi_star_model_file)
    fragprints = compute_fragprints([smiles_string])
    return pi_pi_star_model.predict(fragprints)[0], n_pi_star_model.predict(fragprints)[0]

# %% ../notebooks/04_output.ipynb 49
def predict_photoswitch(smiles: Iterable[str], pi_pi_star_model_file='../models/pi_pi_star_model.joblib', n_pi_star_model_file='../models/n_pi_star_model.joblib'): 
    """Predicting for a single SMILES string. Not really efficient due to the I/O overhead in loading the model."""
    if not isinstance(smiles, Iterable):
        smiles = [smiles]
    pi_pi_star_model = joblib.load(pi_pi_star_model_file)
    n_pi_star_model = joblib.load(n_pi_star_model_file)
    fragprints = compute_fragprints(smiles)
    return pi_pi_star_model.predict(fragprints), n_pi_star_model.predict(fragprints)

# %% ../notebooks/04_output.ipynb 51
_PI_PI_STAR_REGEX = r'pi-pi\* transition wavelength of ([.\d]+) nm'
_N_PI_STAR_REGEX = r'n-pi\* transition wavelength of ([.\d]+) nm'

def get_expected_wavelengths(prompt): 
    pi_pi_star_match = re.search(_PI_PI_STAR_REGEX, prompt)
    n_pi_star_match = re.search(_N_PI_STAR_REGEX, prompt)
    pi_pi_star = float(pi_pi_star_match.group(1)) if pi_pi_star_match else None
    n_pi_star = float(n_pi_star_match.group(1)) if n_pi_star_match else None
    return pi_pi_star, n_pi_star

# %% ../notebooks/04_output.ipynb 55
def test_inverse_photoswitch(
    prompt_frame, model, train_smiles, temperature, max_tokens: int = 80
):
    completions = query_gpt3(
        model, prompt_frame, max_tokens=max_tokens, temperature=temperature
    )
    predictions = np.array(
        [
            extract_inverse_prediction(completions, i)
            for i in range(len(completions["choices"]))
        ]
    )

    valid_smiles = [is_valid_smiles(smiles) for smiles in predictions]

    smiles_in_train = [
        is_string_in_training_data(smiles, train_smiles)
        for smiles in predictions[valid_smiles]
    ]

    expected_pi_pi_star, expected_n_pi_star = [], []

    for prompt in prompt_frame["prompt"].values:
        pi_pi_star, n_pi_star = get_expected_wavelengths(prompt)
        expected_pi_pi_star.append(pi_pi_star)
        expected_n_pi_star.append(n_pi_star)

    expected_pi_pi_star = np.array(expected_pi_pi_star)
    expected_n_pi_star = np.array(expected_n_pi_star)

    has_expected_n_pi_star = np.array(
        [n_pi_star is not None for n_pi_star in expected_n_pi_star]
    )

    try:
        predicted_pi_pi_star, predicted_n_pi_star = predict_photoswitch(
            predictions[valid_smiles]
        )

        predicted_pi_pi_star = predicted_pi_pi_star.flatten()
        predicted_n_pi_star = predicted_n_pi_star.flatten()

        pi_pi_star_metrics = get_regression_metrics(
            expected_pi_pi_star[valid_smiles],
            predicted_pi_pi_star,
        )

        mask_n_valid_smiles = [
            has_expected_n_pi_star[i] for i in range(len(valid_smiles)) if valid_smiles[i]
        ]
        n_pi_star_metrics = get_regression_metrics(
            expected_n_pi_star[valid_smiles & has_expected_n_pi_star],
            np.array(predicted_n_pi_star)[mask_n_valid_smiles],
        )

        error_pi_pi_star = np.abs(expected_pi_pi_star[valid_smiles] - predicted_pi_pi_star)
        error_n_pi_star = np.abs(
            expected_n_pi_star[valid_smiles & has_expected_n_pi_star]
            - np.array(predicted_n_pi_star)[mask_n_valid_smiles]
        )

        min_error_pi_pi_star = predictions[valid_smiles][np.argmin(error_pi_pi_star)]
        min_error_n_pi_star = predictions[valid_smiles & has_expected_n_pi_star][np.argmin(error_n_pi_star)]

        max_error_pi_pi_star = predictions[valid_smiles][np.argmax(error_pi_pi_star)]
        max_error_n_pi_star = predictions[valid_smiles & has_expected_n_pi_star][np.argmax(error_n_pi_star)]

        error_pi_pi_star_w_n = np.abs(
            expected_pi_pi_star[valid_smiles & has_expected_n_pi_star]
            - np.array(predicted_pi_pi_star)[mask_n_valid_smiles]
        )

        total_error_pi_pi_star = error_n_pi_star + error_pi_pi_star_w_n
        min_total_error_pi_pi_star = predictions[valid_smiles & has_expected_n_pi_star][
            np.argmin(total_error_pi_pi_star)
        ]
        max_total_error_pi_pi_star = predictions[valid_smiles & has_expected_n_pi_star][
            np.argmax(total_error_pi_pi_star)
        ]

        mol_similarity_metrics = pd.DataFrame(
            [
                aggregate_array(get_similarity_to_train_mols(smile, train_smiles))
                for smile in predictions[valid_smiles]
            ]
        )
    except Exception:
        smiles_in_train = []
        predicted_pi_pi_star = None
        predicted_n_pi_star = None
        expected_pi_pi_star = None
        expected_n_pi_star = None
        valid_smiles = []
        pi_pi_star_metrics= None
        n_pi_star_metrics = None
        min_error_pi_pi_star = None
        max_error_pi_pi_star = None
        min_error_n_pi_star = None
        max_error_n_pi_star = None
        min_total_error_pi_pi_star = None
        max_total_error_pi_pi_star = None
        mol_similarity_metrics = pd.DataFrame([])

    results = {
        "meta": {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "model": model,
        },
        "predictions": predictions,
        "valid_smiles": valid_smiles,
        "smiles_in_train": smiles_in_train,
        "predicted_pi_pi_star": predicted_pi_pi_star,
        "predicted_n_pi_star": predicted_n_pi_star,
        "expected_pi_pi_star": expected_pi_pi_star,
        "expected_n_pi_star": expected_n_pi_star,
        "fractions_valid_smiles": np.mean(valid_smiles),
        "fractions_smiles_in_train": np.mean(smiles_in_train),
        "pi_pi_star_metrics": pi_pi_star_metrics,
        "n_pi_star_metrics": n_pi_star_metrics,
        "examples": {
            "min_error_pi_pi_star": min_error_pi_pi_star,
            "max_error_pi_pi_star": max_error_pi_pi_star,
            "min_error_n_pi_star": min_error_n_pi_star,
            "max_error_n_pi_star": max_error_n_pi_star,
            "min_total_error_pi_pi_star": min_total_error_pi_pi_star,
            "max_total_error_pi_pi_star": max_total_error_pi_pi_star,
        },
        "mol_similarity_metrics": mol_similarity_metrics,
        "mol_similarity_metrics_mean": mol_similarity_metrics.mean(),
        "mol_similarity_metrics_std": mol_similarity_metrics.std(),
    }

    return results

