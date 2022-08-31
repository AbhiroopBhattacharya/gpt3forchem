# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/01_api_wrappers.ipynb.

# %% auto 0
__all__ = ['fine_tune', 'query_gpt3', 'extract_prediction', 'extract_regression_prediction', 'train_test_loop']

# %% ../notebooks/01_api_wrappers.ipynb 2
import re
import subprocess
import time

import openai
from pycm import ConfusionMatrix
from sklearn.model_selection import train_test_split


# %% ../notebooks/01_api_wrappers.ipynb 5
def fine_tune(
    train_file,  # path to json file with training prompts (column names "prompt" and "completion")
    valid_file,  # path to json file with validation prompts (column names "prompt" and "completion")
    model: str = "ada",  # model type to use. One of "ada", "davinci". "ada" is the default (and cheapest).
):
    """Run the fine tuning of a GPT-3 model via the OpenAI API."""
    result = subprocess.run(
        f"openai api fine_tunes.create -t {train_file} -v {valid_file} -m {model}",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        modelname = re.findall(r"completions.create -m ([\w\d:-]+) -p", result.stdout)[
            0
        ]
        # sync runs with wandb
        subprocess.run("openai wandb sync -n 1", shell=True)
    except Exception:
        print(result.stdout, result.stderr)
    return modelname


# %% ../notebooks/01_api_wrappers.ipynb 8
import pandas as pd
from fastcore.basics import chunked


def query_gpt3(
    model: str,  # name of the model to use, e.g. "ada:ft-personal-2022-08-24-10-41-29"
    df: pd.DataFrame,  # dataframe with prompts and expected completions (column names "prompt" and "completion")
    temperature: float = 0,  # temperature, 0 is the default and corresponds to argmax
    max_tokens: int = 10,  # maximum number of tokens to generate
    sleep: float = 5,  # number of seconds to wait between queries
    one_by_one: bool = False,  # if True, generate one completion at a time (i.e., due to submit the maximum number of prompts per request)
    parallel_max: int = 20,  # maximum number of prompts that can be sent per request
):
    """Get completions for all prompts in a dataframe."""
    if one_by_one:
        completions = []
        for i, row in df.iterrows():
            try:
                completion = openai.Completion.create(
                    model=model,
                    prompt=row["prompt"],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                completions.append(completion)
                time.sleep(sleep)
            except Exception as e:
                print(e)
                print(f"Error on row {i}")
                completions.append(None)
    else:
        # they have a limit on the maximum number of parallel completions
        # otherwise you get
        # openai.error.InvalidRequestError: Too many parallel completions requested.
        # You submitted 500 prompts, but you can currently request up to at most a total of 20).
        # Please contact support@openai.com and tell us about your use-case if you would like this limit increased.
        # (HINT: if you want to just evaluate probabilities without generating new text, you can submit more prompts if you set 'max_tokens' to 0.)
        completions = []
        for chunk in chunked(df["prompt"], parallel_max):
            completions_ = openai.Completion.create(
                model=model,
                prompt=chunk,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            completions.append(completions_)
            time.sleep(sleep)

        completions = {
            "choices": [choice for c in completions for choice in c["choices"]],
        }

    return completions


# %% ../notebooks/01_api_wrappers.ipynb 9
def extract_prediction(
    completion,  # dictionary with "choices" key returned by the API
    i: int = 0,  # index of the "choice" (relevant if multiple completions have been returned)
) -> str:
    return completion["choices"][i]["text"].split("@")[0].strip()


# %% ../notebooks/01_api_wrappers.ipynb 12
def extract_regression_prediction(
    completion,  # dictionary with "choices" key returned by the API
    i: int = 0,  # index of the "choice" (relevant if multiple completions have been returned)
) -> float:
    """Similar to `extract_prediction`, but returns a float."""
    return float(completion["choices"][i]["text"].split("@")[0].strip())


# %% ../notebooks/01_api_wrappers.ipynb 15
def train_test_loop(
    df, train_size, prompt_create_fn, random_state, stratify=None, test_subset=None
):

    out = {}
    train, test = train_test_split(
        df, train_size=train_size, random_state=random_state, stratify=stratify
    )

    train_prompts = prompt_create_fn(train)
    test_prompts = prompt_create_fn(test)

    train_size = len(train_prompts)
    test_size = len(test_prompts)

    filename_base = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
    train_filename = (
        f"run_files/{filename_base}_train_prompts_polymers_{train_size}.jsonl"
    )
    valid_filename = (
        f"run_files/{filename_base}_valid_prompts_polymers_{test_size}.jsonl"
    )

    train_prompts.to_json(train_filename, orient="records", lines=True)
    test_prompts.to_json(valid_filename, orient="records", lines=True)

    out["train_filename"] = train_filename
    out["valid_filename"] = valid_filename
    out["modelname"] = fine_tune(train_filename, valid_filename)

    test_prompt_subset = test_prompts
    if test_subset is not None:
        test_prompt_subset = test_prompts.sample(test_subset)
    completions = query_gpt3(out["modelname"], test_prompt_subset)

    ok_completions = [(i, c) for i, c in enumerate(completions) if c is not None]

    predictions = [extract_prediction(completion) for _, completion in ok_completions]
    true = [
        int(test_prompt_subset.iloc[i]["completion"].split("@")[0])
        for i, _ in ok_completions
    ]
    cm = ConfusionMatrix(true, predictions)

    out["cm"] = cm

    return out

