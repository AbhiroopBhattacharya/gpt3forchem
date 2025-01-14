import time

import click
import pandas as pd
from fastcore.xtras import save_pickle
from pycm import ConfusionMatrix
from sklearn.model_selection import train_test_split

from gpt3forchem.api_wrappers import extract_prediction, fine_tune, query_gpt3
from gpt3forchem.baselines import train_test_gpr_baseline
from gpt3forchem.data import get_photoswitch_data
from gpt3forchem.helpers import augmented_classification_scores, make_if_not_exists
from gpt3forchem.input import create_single_property_forward_prompts

TRAIN_SIZES_NAMES = [10, 40, 60, 70]
TRAIN_SIZES_SMILES = [10, 50, 100, 200, 300, 350]

REPRESENTATIONS = ["SMILES", "selfies", "name"]

REPEATS = 10
DF = get_photoswitch_data()
MODEL_TYPE = "ada"
PREFIX = ""
N_EPOCHS = 4  # this is the default
OUTDIR = "results/20220913_photoswitch_augment"
make_if_not_exists(OUTDIR)


def learning_curve_point(representation, model_type, train_set_size, include_canonical):
    df = DF.dropna(subset=[representation])
    df_train, df_test = train_test_split(
        df, train_size=train_set_size, random_state=None, stratify=df["wavelength_cat"]
    )

    train_size = len(df_train)
    test_size = len(df_test)

    train_prompts = create_single_property_forward_prompts(
        df_train,
        "wavelength_cat",
        {"wavelength_cat": "transition wavelength"},
        representation_col=representation,
        smiles_augmentation=True,
        include_canonical_smiles=include_canonical,
    )

    test_prompts = create_single_property_forward_prompts(
        df_test,
        "wavelength_cat",
        {"wavelength_cat": "transition wavelength"},
        representation_col=representation,
        smiles_augmentation=True,
        include_canonical_smiles=include_canonical,
    )

    filename_base = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
    train_filename = f"run_files/{filename_base}_train_prompts_photoswitch_{train_size}_{representation}.jsonl"
    valid_filename = f"run_files/{filename_base}_valid_prompts_photoswitch_{test_size}_{representation}.jsonl"

    train_prompts.to_json(train_filename, orient="records", lines=True)
    test_prompts.to_json(valid_filename, orient="records", lines=True)

    print(f"Training {model_type} model on {train_size} training examples")
    modelname = fine_tune(train_filename, valid_filename, model_type, n_epochs=N_EPOCHS)

    completions = query_gpt3(modelname, test_prompts)
    predictions = [
        extract_prediction(completions, i)
        for i, completion in enumerate(completions["choices"])
    ]
    true = [
        int(test_prompts.iloc[i]["completion"].split("@")[0])
        for i in range(len(predictions))
    ]
    smiles = test_prompts["repr"]
    assert len(predictions) == len(true) == len(smiles)

    cm, brier, ece = augmented_classification_scores(
        smiles, true, predictions, cat_encode_func=None
    )
    prediction_frame = pd.DataFrame(
        {
            "smiles": smiles,
            "prediction": predictions,
            "true": true,
        }
    )

    # if we use the canonical smiles, we should also get the predictions for the different subsets:
    # canonical, augmented, and canonical + augmented
    if include_canonical:
        canonical_subset_mask = test_prompts["repr"] == test_prompts["this_repr"]
        canonical_predictions = prediction_frame["prediction"][canonical_subset_mask]
        canonical_true = prediction_frame["true"][canonical_subset_mask]
        cm_canonical_subset = ConfusionMatrix(
            canonical_true.to_list(), canonical_predictions.to_list()
        )

        augmented_subset_mask = test_prompts["repr"] != test_prompts["this_repr"]
        augmented_predictions = prediction_frame["prediction"][augmented_subset_mask]
        augmented_true = prediction_frame["true"][augmented_subset_mask]
        (
            cm_augmented_subset,
            brier_augmented_subset,
            ece_augmented_subset,
        ) = augmented_classification_scores(
            prediction_frame["smiles"][augmented_subset_mask],
            augmented_true,
            augmented_predictions,
            cat_encode_func=None,
        )
    else:
        cm_canonical_subset = None
        cm_augmented_subset = None
        brier_augmented_subset = None
        ece_augmented_subset = None

    baseline = train_test_gpr_baseline(
        train_filename, valid_filename, representation_column=representation
    )
    results = {
        "model_type": model_type,
        "train_set_size": train_set_size,
        # "prefix": prefix,
        "train_size": train_size,
        "test_size": test_size,
        "augmented_size_train": len(train_prompts),
        "augmented_size_test": len(test_prompts),
        "cm": cm,
        "brier": brier,
        "ece": ece,
        "include_canonical": include_canonical,
        "subset_scores": {
            "canonical": cm_canonical_subset,
            "augmented": cm_augmented_subset,
            "brier_augmented": brier_augmented_subset,
            "ece_augmented": ece_augmented_subset,
        },
        "accuracy": cm.ACC_Macro,
        "completions": completions,
        "train_filename": train_filename,
        "valid_filename": valid_filename,
        "modelname": modelname,
        "baseline": baseline,
        "representation": representation,
        "baseline_accuracy": baseline["cm"].ACC_Macro,
    }

    outname = f"{OUTDIR}/{filename_base}_results_photoswitch_{train_size}_{model_type}_{representation}_{include_canonical}.pkl"

    save_pickle(outname, results)
    return results


@click.command("cli")
@click.argument("representation", type=click.Choice(REPRESENTATIONS))
@click.option("--include-canonical", default=False, is_flag=True)
def run_lc(representation, include_canonical):
    for _ in range(REPEATS):
        if representation == "name":
            train_sizes = TRAIN_SIZES_NAMES
        else:
            train_sizes = TRAIN_SIZES_SMILES
        for train_size in train_sizes:
            try:
                res = learning_curve_point(
                    representation,
                    MODEL_TYPE,
                    train_size,
                    include_canonical=include_canonical,
                )
                print(
                    f"Finished {representation} {train_size} {include_canonical}. Accuracy: {res['accuracy']}. Baseline accuracy: {res['baseline_accuracy']}"
                )
                time.sleep(1)
            except Exception as e:
                print(f"Error: {e}")
                continue


if __name__ == "__main__":
    run_lc()
