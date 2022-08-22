# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/03_input.ipynb.

# %% auto 0
__all__ = ['ONE_PROPERTY_FORWARD_PROMPT_TEMPLATE', 'ONE_PROPERTY_FORWARD_COMPLETION_TEMPLATE',
           'POLYMER_ONE_PROPERTY_INVERSE_PROMPT_TEMPLATE_CAT', 'POLYMER_ONE_PROPERTY_INVERSE_COMPLETION_TEMPLATE_CAT',
           'POLYMER_ONE_PROPERTY_INVERSE_PROMPT_TEMPLATE_CAT_W_COMPOSITION', 'encode_categorical_value',
           'decode_categorical_value', 'create_single_property_forward_prompts',
           'create_single_property_forward_prompts_regression', 'get_polymer_composition_dict']

# %% ../notebooks/03_input.ipynb 2
import pandas as pd
from collections import Counter

_DEFAULT_ENCODING_DICT = {
    "very small": 0,
    "small": 1,
    "medium": 2,
    "large": 3,
    "very large": 4,
}

_DEFAULT_DECODING_DICT = {v: k for k, v in _DEFAULT_ENCODING_DICT.items()}


def encode_categorical_value(value, encoding_dict=_DEFAULT_DECODING_DICT):
    try:
        return encoding_dict[value]
    except KeyError:
        raise ValueError("Unknown value: %s" % value)


def decode_categorical_value(value, decoding_dict=_DEFAULT_DECODING_DICT):
    try:
        return decoding_dict[value]
    except KeyError:
        raise ValueError("Unknown value: %s" % value)


# %% ../notebooks/03_input.ipynb 3
ONE_PROPERTY_FORWARD_PROMPT_TEMPLATE = "what is the {property} of {text}###"
ONE_PROPERTY_FORWARD_COMPLETION_TEMPLATE = " {value}@@@"


# %% ../notebooks/03_input.ipynb 4
def create_single_property_forward_prompts(
    df, # input data
    target, # target property
    target_rename_dict, # dict to rename target property from the column name in df to the target property name in the prompt
    encode_value=True, # whether to encode the value of the target property categorically
    encoding_dict=_DEFAULT_ENCODING_DICT, # mapping from numerical categories to string
    prompt_prefix="", # prefix to add to the prompt, e.g. "I am an expert chemist"
):
    prompts = []

    target_name = target
    for key, value in target_rename_dict.items():
        target_name = target_name.replace(key, value)

    for _, row in df.iterrows():
        if encode_value:
            value = encode_categorical_value(row[target], encoding_dict=encoding_dict)
        else:
            value = row[target]

        prompts.append(
            {
                "prompt": prompt_prefix
                + ONE_PROPERTY_FORWARD_PROMPT_TEMPLATE.format(
                    property=target_name, text=row["string"]
                ),
                "completion": ONE_PROPERTY_FORWARD_COMPLETION_TEMPLATE.format(
                    value=value
                ),
            }
        )

    return pd.DataFrame(prompts)


# %% ../notebooks/03_input.ipynb 7
def create_single_property_forward_prompts_regression(
    df, # input data
    target, # target property
    target_rename_dict, # dict to rename target property from the column name in df to the target property name in the prompt
    prompt_prefix="", # prefix to add to the prompt, e.g. "I am an expert chemist"
    num_digit=1,
):
    prompts = []

    target_name = target
    for key, value in target_rename_dict.items():
        target_name = target_name.replace(key, value)

    for _, row in df.iterrows():

        value = f"{round(row[target], num_digit)}"

        prompts.append(
            {
                "prompt": prompt_prefix
                + ONE_PROPERTY_FORWARD_PROMPT_TEMPLATE.format(
                    property=target_name, text=row["string"]
                ),
                "completion": ONE_PROPERTY_FORWARD_COMPLETION_TEMPLATE.format(
                    value=value
                ),
            }
        )

    return pd.DataFrame(prompts)


# %% ../notebooks/03_input.ipynb 10
POLYMER_ONE_PROPERTY_INVERSE_PROMPT_TEMPLATE_CAT = (
    "what is a polymer with {class_name} {property}?###"
)
POLYMER_ONE_PROPERTY_INVERSE_COMPLETION_TEMPLATE_CAT = " {text}@@@"

POLYMER_ONE_PROPERTY_INVERSE_PROMPT_TEMPLATE_CAT_W_COMPOSITION = "what is a polymer with {class_name} {property} and {num_A} A, {num_B} B, {num_W} W, and {num_R} R?###"


# %% ../notebooks/03_input.ipynb 11
def get_polymer_composition_dict(row):
    composition = Counter(row["string"].split("-"))
    comp_dict = {}
    for key in ["A", "B", "R", "W"]:
        try:
            count = composition[key]
        except KeyError:
            count = 0
        comp_dict[f"num_{key}"] = count
    return comp_dict

