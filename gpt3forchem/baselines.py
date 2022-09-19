# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/05_baselines.ipynb.

# %% auto 0
__all__ = ['BaseLineModel', 'XGBClassificationBaseline', 'XGBRegressionBaseline', 'create_mof_w_context_frame',
           'upper_bound_context_baseline', 'lower_bound_context_baselines', 'chemistry_encoded_context_baseline',
           'Tanimoto', 'compute_morgan_fingerprints', 'compute_fragprints', 'GPRBaseline', 'train_test_gpr_baseline']

# %% ../notebooks/05_baselines.ipynb 1
from abc import ABC, abstractmethod
from typing import Iterable

import gpflow
import numpy as np
import pandas as pd
import tensorflow as tf
from gpflow.mean_functions import Constant
from gpflow.utilities import positive, print_summary
from gpflow.utilities.ops import broadcasting_elementwise
from nbdev.showdoc import *
from optuna import create_study
from optuna.integration import XGBoostPruningCallback
from optuna.samplers import TPESampler
from pycm import ConfusionMatrix
from rdkit.Chem import AllChem, Descriptors, MolFromSmiles, MolToSmiles
from sklearn.metrics import accuracy_score, f1_score, mean_squared_error
from sklearn.model_selection import KFold
from sklearn.preprocessing import LabelEncoder, StandardScaler
from wandb.xgboost import WandbCallback
from xgboost import XGBClassifier, XGBRegressor

from .data import get_photoswitch_data

# %% ../notebooks/05_baselines.ipynb 3
class BaseLineModel(ABC):
    @abstractmethod
    def tune(self, X_train, y_train):
        raise NotImplementedError()

    @abstractmethod
    def fit(self, X_train, y_train):
        raise NotImplementedError()

    @abstractmethod
    def predict(self, X):
        raise


# %% ../notebooks/05_baselines.ipynb 4
class XGBClassificationBaseline(BaseLineModel):
    def __init__(self, seed, num_trials=100, timeout=None) -> None:
        self.seed = seed
        self.num_trials = num_trials
        self.model = XGBClassifier()
        self.timeout = timeout

        self.label_encoder = LabelEncoder()

    def tune(self, X_train, y_train):
        y_train = self.label_encoder.fit_transform(y_train)

        def objective(
            trial,
            X,
            y,
            random_state=22,
            n_splits=5,
            n_jobs=1,
        ):
            # XGBoost parameters
            params = {
                "verbosity": 0,  # 0 (silent) - 3 (debug)
                "n_estimators": trial.suggest_int("n_estimators", 4, 10_000),
                "max_depth": trial.suggest_int("max_depth", 4, 50),
                "learning_rate": trial.suggest_loguniform("learning_rate", 0.001, 0.05),
                "colsample_bytree": trial.suggest_loguniform(
                    "colsample_bytree", 0.2, 1
                ),
                "subsample": trial.suggest_loguniform("subsample", 0.00001, 1),
                "alpha": trial.suggest_loguniform("alpha", 1e-8, 10.0),
                "lambda": trial.suggest_loguniform("lambda", 1e-8, 10.0),
                "seed": random_state,
                "n_jobs": n_jobs,
            }

            model = XGBClassifier(**params)
            #pruning_callback = XGBoostPruningCallback(trial, "validation_0-mlogloss")
            kf = KFold(n_splits=n_splits)
            X_values = X.values
            y_values = y

            scores = []
            for train_index, test_index in kf.split(X_values):
                X_A, X_B = X_values[train_index, :], X_values[test_index, :]
                y_A, y_B = y_values[train_index], y_values[test_index]

                model.fit(
                    X_A,
                    y_A,
                    eval_set=[(X_B, y_B)],
                    #eval_metric="mlogloss",
                    verbose=0,
                    #callbacks=[pruning_callback],
                )
                y_pred = model.predict(X_B)
                scores.append(f1_score(y_pred, y_B, average="macro"))
            return np.mean(scores)

        sampler = TPESampler(seed=self.seed)
        study = create_study(direction="maximize", sampler=sampler)
        study.optimize(
            lambda trial: objective(
                trial,
                X_train,
                y_train,
                random_state=self.seed,
                n_splits=5,
                n_jobs=1,
                
            ),
            n_trials=self.num_trials,
            n_jobs=1,
            timeout=self.timeout,
        )   

        print(**study.best_params)
        self.model = XGBClassifier(**study.best_params)

    def fit(self, X_train, y_train):
        y_train = self.label_encoder.fit_transform(y_train)
        self.model.fit(X_train.values, y_train, verbosity=1)
        return self.model

    def predict(self, X):
        return self.label_encoder.inverse_transform(self.model.predict(X.values))


# %% ../notebooks/05_baselines.ipynb 5
class XGBRegressionBaseline(BaseLineModel):
    def __init__(self, seed, num_trials=100) -> None:
        self.seed = seed
        self.num_trials = num_trials
        self.model = XGBRegressor()

    def tune(self, X_train, y_train):
        def objective(
            trial,
            X,
            y,
            random_state=22,
            n_splits=5,
            n_jobs=1,
            early_stopping_rounds=50,
        ):
            # XGBoost parameters
            params = {
                "verbosity": 0,  # 0 (silent) - 3 (debug)
                "objective": "reg:squarederror",
                "n_estimators": 10000,
                "max_depth": trial.suggest_int("max_depth", 4, 12),
                "learning_rate": trial.suggest_loguniform("learning_rate", 0.005, 0.05),
                "colsample_bytree": trial.suggest_uniform(
                    "colsample_bytree", 0.2, 0.6 # note: log uniform was used before
                ),
                "subsample": trial.suggest_uniform("subsample", 0.4, 0.8), # note: log uniform was used before
                "alpha": trial.suggest_loguniform("alpha", 0.01, 10.0),
                "lambda": trial.suggest_loguniform("lambda", 1e-8, 10.0),
                "gamma": trial.suggest_loguniform("gamma", 1e-8, 10.0), # note: this was wrong before (lambda was used as name) 
                "min_child_weight": trial.suggest_loguniform(
                    "min_child_weight", 10, 1000
                ),
                "seed": random_state,
                "n_jobs": n_jobs,
            }

            model = XGBRegressor(**params)
           
            kf = KFold(n_splits=n_splits)
            X_values = X.values
            y_values = y.values
            scores = []
            for train_index, test_index in kf.split(X_values):
                X_A, X_B = X_values[train_index, :], X_values[test_index, :]
                y_A, y_B = y_values[train_index], y_values[test_index]
                model.fit(
                    X_A,
                    y_A,
                    eval_set=[(X_B, y_B)],
                    eval_metric="rmse",
                    verbose=0, 
                    early_stopping_rounds=early_stopping_rounds,
                )
                y_pred = model.predict(X_B)
                scores.append(mean_squared_error(y_pred, y_B))
            return np.mean(scores)

        sampler = TPESampler(seed=self.seed)
        study = create_study(direction="minimize", sampler=sampler)
        study.optimize(
            lambda trial: objective(
                trial,
                X_train,
                y_train,
                random_state=self.seed,
                n_splits=5,
                n_jobs=8,
                early_stopping_rounds=100,
                
            ),
            n_trials=self.num_trials,
            n_jobs=1,
        )

        self.model = XGBRegressor(**study.best_params)

    def fit(self, X_train, y_train):
        self.model.fit(X_train.values, y_train)

    def predict(self, X):
        return self.model.predict(X.values)


# %% ../notebooks/05_baselines.ipynb 8
def create_mof_w_context_frame(
    df, gas_frame, gases, gas_properties, features, regression: bool = False
):
    frame = []

    for i, row in df.iterrows():
        for gas in gases:
            subset = gas_frame[gas_frame["formula"] == gas]
            column = subset["related_column"].values[0]
            if (not pd.isna(row[column])) and (not "nan" in str(row[column]).lower()):

                mof_feats = dict(row[features])

                if gas_properties:
                    gast_feats = {prop: subset[prop].values[0] for prop in gas_properties}
                    mof_feats.update(gast_feats)

                mof_feats["target"] = row[column]

                frame.append(mof_feats)

    return pd.DataFrame(frame)


# %% ../notebooks/05_baselines.ipynb 17
def upper_bound_context_baseline(
    train_df,
    test_df,
    representation="info.mofid.mofid_clean",
    target="outputs.H2O-henry_coefficient-mol--kg--Pa_log_cat",
    target_rename_dict={
        "outputs.H2O-henry_coefficient-mol--kg--Pa_log_cat": "H2O Henry coefficient"
    },
):
    # train GPT3 directly on water
    test_prompts = create_single_property_forward_prompts(
        test_df,
        target,
        target_rename_dict,
        representation_col=representation,
        encode_value=False,
    )

    test_prompts = create_single_property_forward_prompts(
        test_df,
        target,
        target_rename_dict,
        representation_col=representation,
        encode_value=False,
    )

    filename_base = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
    train_filename = f"run_files/{filename_base}_train_prompts_mof_bl.jsonl"
    valid_filename = f"run_files/{filename_base}_valid_prompts_mof_bl.jsonl"

    train_prompts.to_json(train_filename, orient="records", lines=True)
    test_prompts.to_json(valid_filename, orient="records", lines=True)

    modelname = fine_tune(train_filename, valid_filename)

    completions = query_gpt3(modelname, test_prompts)
    predictions = [
        extract_prediction(completions, i) for i in range(len(completions["choices"]))
    ]
    true = test_prompts["completion"].apply(lambda x: x.split("@")[0].strip())
    cm = ConfusionMatrix(actual_vector=true.to_list(), predict_vector=predictions)

    results = {
        "train_filename": train_filename,
        "valid_filename": valid_filename,
        "modelname": modelname,
        "completions": completions,
        "cm": cm,
        "accuracy": cm.ACC_Macro,
        "train_size": len(train_df),
        "test_size": len(test_df),
        "representation": representation,
    }

    return results


# %% ../notebooks/05_baselines.ipynb 18
def lower_bound_context_baselines(
    train_df, test_df, target="outputs.H2O-henry_coefficient-mol--kg--Pa_log_cat"
):
    test_true = test_df[target].to_list()
    train_true = train_df[target].to_list()

    # Dummy Classifier
    random = DummyClassifier(strategy="uniform")
    most_frequent = DummyClassifier(strategy="most_frequent")
    stratified = DummyClassifier(strategy="stratified")

    random.fit(train_true, train_true)
    most_frequent.fit(train_true, train_true)
    stratified.fit(train_true, train_true)

    random_preds = random.predict(test_true)
    most_frequent_preds = most_frequent.predict(test_true)
    stratified_preds = stratified.predict(test_true)

    random_cm = ConfusionMatrix(actual_vector=test_true, predict_vector=random_preds)
    most_frequent_cm = ConfusionMatrix(
        actual_vector=test_true, predict_vector=most_frequent_preds
    )
    stratified_cm = ConfusionMatrix(
        actual_vector=test_true, predict_vector=stratified_preds
    )

    results = {
        "random": {
            "cm": random_cm,
            "accuracy": random_cm.ACC_Macro,
        },
        "most_frequent": {
            "cm": most_frequent_cm,
            "accuracy": most_frequent_cm.ACC_Macro,
        },
        "stratified": {
            "cm": stratified_cm,
            "accuracy": stratified_cm.ACC_Macro,
        },
        "train_size": len(train_df),
        "test_size": len(test_df),
    }
    return results


# %% ../notebooks/05_baselines.ipynb 19
def chemistry_encoded_context_baseline(train_df, test_df, features, train_gases, test_gases, gas_properties, random_seed=None, tune=True):

    train_frame  = create_mof_w_context_frame(df=train_df, gas_frame=gas_features, gases=train_gases, gas_properties=gas_properties, features=features)
    test_frame = create_mof_w_context_frame(df=test_df, gas_frame=gas_features, gases=test_gases, gas_properties=gas_properties, features=features)

    feat = features + gas_properties

    xgb = XGBClassificationBaseline(random_seed)
    if tune:
        xgb.tune(train_frame[feat], train_frame['target'])
    xgb.fit(train_frame[feat], train_frame['target'])

    preds = xgb.predict(test_frame[feat])
    true = test_frame['target'].to_list()
    cm = ConfusionMatrix(actual_vector=true, predict_vector=preds)
    return {
        "cm": cm,
        "accuracy": cm.ACC_Macro,
    }

# %% ../notebooks/05_baselines.ipynb 22
class Tanimoto(gpflow.kernels.Kernel):
    """Tanimoto kernel.

    Taken from https://github.com/Ryan-Rhys/The-Photoswitch-Dataset/blob/master/property_prediction/kernels.py.
    """

    def __init__(self, **kwargs):
        """
        :param kwargs: accepts `name` and `active_dims`, which is a list or
            slice of indices which controls which columns of X are used (by
            default, all columns are used).
        """
        for kwarg in kwargs:
            if kwarg not in {"name", "active_dims"}:
                raise TypeError("Unknown keyword argument:", kwarg)
        super().__init__(**kwargs)
        self.variance = gpflow.Parameter(1.0, transform=positive())

    def K(self, X, X2=None):
        """
        Compute the Tanimoto kernel matrix σ² * ((<x, y>) / (||x||^2 + ||y||^2 - <x, y>))
        :param X: N x D array
        :param X2: M x D array. If None, compute the N x N kernel matrix for X.
        :return: The kernel matrix of dimension N x M
        """
        if X2 is None:
            X2 = X

        Xs = tf.reduce_sum(tf.square(X), axis=-1)  # Squared L2-norm of X
        X2s = tf.reduce_sum(tf.square(X2), axis=-1)  # Squared L2-norm of X2
        cross_product = tf.tensordot(
            X, X2, [[-1], [-1]]
        )  # outer product of the matrices X and X2

        # Analogue of denominator in Tanimoto formula

        denominator = -cross_product + broadcasting_elementwise(tf.add, Xs, X2s)

        return self.variance * cross_product / denominator

    def K_diag(self, X):
        """
        Compute the diagonal of the N x N kernel matrix of X
        :param X: N x D array
        :return: N x 1 array
        """
        return tf.fill(tf.shape(X)[:-1], tf.squeeze(self.variance))


# %% ../notebooks/05_baselines.ipynb 23
def compute_morgan_fingerprints(smiles_list: Iterable[str] # list of SMILEs
) -> np.ndarray:
    rdkit_mols = [MolFromSmiles(smiles) for smiles in smiles_list]
    rdkit_smiles = [MolToSmiles(mol, isomericSmiles=False) for mol in rdkit_mols]
    rdkit_mols = [MolFromSmiles(smiles) for smiles in rdkit_smiles]
    X = [
        AllChem.GetMorganFingerprintAsBitVect(mol, 3, nBits=2048)
        for mol in rdkit_mols
    ]
    X = np.asarray(X)
    return X

def compute_fragprints(
    smiles_list: Iterable[str] # list of SMILEs
) -> np.ndarray:
    X = compute_morgan_fingerprints(smiles_list)

    fragments = {d[0]: d[1] for d in Descriptors.descList[115:]}
    X1 = np.zeros((len(smiles_list), len(fragments)))
    for i in range(len(smiles_list)):
        mol = MolFromSmiles(smiles_list[i])
        try:
            features = [fragments[d](mol) for d in fragments]
        except:
            raise Exception("molecule {}".format(i) + " is not canonicalised")
        X1[i, :] = features

    X = np.concatenate((X, X1), axis=1)
    return X

# %% ../notebooks/05_baselines.ipynb 26
class GPRBaseline(BaseLineModel):
    """GPR w/ Tanimoto kernel baseline."""
    def __init__(self) -> None:
        self.model = None
        self.y_scaler = StandardScaler()

    def tune(
        self,
        X_train: np.ndarray, # N x D features
        y_train: np.ndarray  # N x 1 target
    ):
        pass

    def fit(
        self,
        X_train: np.ndarray, # N x D features
        y_train: np.ndarray  # N x 1 target
    ):
        y_train = y_train.reshape(-1, 1)

        def objective_closure():
            return -m.log_marginal_likelihood()

        y_train = self.y_scaler.fit_transform(y_train)

        m = gpflow.models.GPR(
            data=(X_train, y_train),
            mean_function=Constant(np.mean(y_train)),
            kernel=Tanimoto(),
            noise_variance=1,
        )

        # Optimise the kernel variance and noise level by the marginal likelihood
        opt = gpflow.optimizers.Scipy()
        opt.minimize(
            objective_closure, m.trainable_variables, options=dict(maxiter=10000)
        )
        print_summary(m)
        self.model = m

    def predict(
            self, 
            X_test: np.ndarray # N x D features
        ):  
        y_pred, y_var = self.model.predict_f(X_test)
        y_pred = self.y_scaler.inverse_transform(y_pred)
        return y_pred


# %% ../notebooks/05_baselines.ipynb 37
def train_test_gpr_baseline(train_file, test_file, delete_from_prompt: str = 'what is the transition wavelength of', representation_column: str = 'SMILES'): 
    df = get_photoswitch_data()
    train_frame = pd.read_json(train_file, orient="records", lines=True)
    test_frame = pd.read_json(test_file, orient="records", lines=True)


    repr_train = train_frame['repr']
    repr_test = test_frame['repr']
    y_train = np.array([df[df[representation_column]==smile]['E isomer pi-pi* wavelength in nm'].values[0] for smile in repr_train])
    y_test = np.array([df[df[representation_column]==smile]['E isomer pi-pi* wavelength in nm'].values[0] for smile in repr_test])

    if representation_column =='SMILES': 
        smiles_train = repr_train
        smiles_test = repr_test
    else: 
        smiles_train = np.array([df[df[representation_column]==smile]['SMILES'].values[0] for smile in repr_train])
        smiles_test = np.array([df[df[representation_column]==smile]['SMILES'].values[0] for smile in repr_test]) 

    df_train = pd.DataFrame(
        {
            "SMILES": smiles_train,
            'y': y_train
        }
    )
    df_test = pd.DataFrame(
        {
            "SMILES": smiles_test,
            'y': y_test
        }
    )

    df_train = df_train.drop_duplicates(subset=['SMILES'])
    df_test = df_test.drop_duplicates(subset=['SMILES'])

    X_train = compute_fragprints(df_train['SMILES'].values)
    X_test = compute_fragprints(df_test['SMILES'].values)

    baseline = GPRBaseline()
    baseline.fit(X_train, df_train['y'].values)

    predictions = baseline.predict(X_test)

    _, bins = pd.cut(df['E isomer pi-pi* wavelength in nm'], 5, retbins=True)

    # we clip as out-of-bound predictions result in NaNs
    pred = np.clip(predictions.flatten(), a_min=bins[0], a_max=bins[-1])
    predicted_bins = pd.cut(pred, bins, labels=np.arange(5), include_lowest=True)
    true_bins = pd.cut(df_test['y'].values.flatten(), bins, labels=np.arange(5))

    cm = ConfusionMatrix(true_bins.astype(int), predicted_bins.astype(int))

    return {
        'true_bins': true_bins,
        'predicted_bins': predicted_bins,
        'cm': cm,
        'predictions': predictions
    }
