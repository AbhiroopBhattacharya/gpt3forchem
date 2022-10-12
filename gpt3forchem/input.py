# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/03_input.ipynb.

# %% auto 0
__all__ = ['ONE_PROPERTY_FORWARD_PROMPT_TEMPLATE', 'ONE_PROPERTY_FORWARD_COMPLETION_TEMPLATE',
           'POLYMER_ONE_PROPERTY_INVERSE_PROMPT_TEMPLATE_CAT', 'POLYMER_ONE_PROPERTY_INVERSE_COMPLETION_TEMPLATE_CAT',
           'POLYMER_ONE_PROPERTY_INVERSE_PROMPT_TEMPLATE_CAT_W_COMPOSITION', 'PROMPT_TEMPLATE_photoswitch_w_n_pistar',
           'PROMPT_TEMPLATE_photoswitch_', 'COMPLETION_TEMPLATE_photoswitch_', 'randomize_smiles',
           'encode_categorical_value', 'decode_categorical_value', 'create_single_property_forward_prompts',
           'create_single_property_forward_prompts_regression', 'get_polymer_composition_dict',
           'create_single_property_inverse_polymer_prompts', 'generate_inverse_photoswitch_prompts',
           'generate_property_desc', 'create_prompts_w_gas_context', 'create_mof_yield_prompt',
           'get_mof_yield_prompt_completions']

# %% ../notebooks/03_input.ipynb 1
import random
from typing import List

from rdkit import Chem
import numpy as np
import pandas as pd

# %% ../notebooks/03_input.ipynb 4
def randomize_smiles(
    smiles: str,
    random_type: str = "rotated",  #  The type (unrestricted, restricted, rotated) of randomization performed.
    isomericSmiles: bool = True,
):
    """
    From: https://github.com/undeadpixel/reinvent-randomized and https://github.com/GLambard/SMILES-X
    Returns a random SMILES given a SMILES of a molecule.
    """
    mol = Chem.MolFromSmiles(smiles)
    if not mol:
        return None

    if random_type == "unrestricted":
        return Chem.MolToSmiles(
            mol, canonical=False, doRandom=True, isomericSmiles=isomericSmiles
        )
    elif random_type == "restricted":
        new_atom_order = list(range(mol.GetNumAtoms()))
        random.shuffle(new_atom_order)
        random_mol = Chem.RenumberAtoms(mol, newOrder=new_atom_order)
        return Chem.MolToSmiles(
            random_mol, canonical=False, isomericSmiles=isomericSmiles
        )
    elif random_type == "rotated":
        n_atoms = mol.GetNumAtoms()
        rotation_index = random.randint(0, n_atoms - 1)
        atoms = list(range(n_atoms))
        new_atoms_order = (
            atoms[rotation_index % len(atoms) :] + atoms[: rotation_index % len(atoms)]
        )
        rotated_mol = Chem.RenumberAtoms(mol, new_atoms_order)
        return Chem.MolToSmiles(
            rotated_mol, canonical=False, isomericSmiles=isomericSmiles
        )
    raise ValueError("Type '{}' is not valid".format(random_type))


# %% ../notebooks/03_input.ipynb 7
from collections import Counter

import numpy as np
import pandas as pd


# %% ../notebooks/03_input.ipynb 8
_DEFAULT_ENCODING_DICT = {
    "very small": 0,
    "small": 1,
    "medium": 2,
    "large": 3,
    "very large": 4,
}

_DEFAULT_DECODING_DICT = {v: k for k, v in _DEFAULT_ENCODING_DICT.items()}


def encode_categorical_value(value, encoding_dict=_DEFAULT_ENCODING_DICT):
    try:
        return encoding_dict[value]
    except KeyError:
        raise ValueError("Unknown value: %s" % value)


def decode_categorical_value(value, decoding_dict=_DEFAULT_DECODING_DICT):
    try:
        return decoding_dict[value]
    except KeyError:
        raise ValueError("Unknown value: %s" % value)


# %% ../notebooks/03_input.ipynb 9
ONE_PROPERTY_FORWARD_PROMPT_TEMPLATE = "what is the {property} of {text}###"
ONE_PROPERTY_FORWARD_COMPLETION_TEMPLATE = " {value}@@@"


# %% ../notebooks/03_input.ipynb 10
def create_single_property_forward_prompts(
    df: pd.DataFrame,  # input data
    target: str,  # target property
    target_rename_dict: dict,  # dict to rename target property from the column name in df to the target property name in the prompt
    encode_value: bool = True,  # whether to encode the value of the target property categorically
    encoding_dict: dict = _DEFAULT_ENCODING_DICT,  # mapping from numerical categories to string
    prompt_prefix: str = "",  # prefix to add to the prompt, e.g. "I am an expert chemist"
    representation_col: str = "string",  # name of the column to use as the representation of the compound
    smiles_augmentation: bool = False,  # whether to augment the SMILES with randomization
    smiles_augmentation_type: str = "rotated",  # the type of randomization to perform
    smiles_augmentation_rounds: int = 10,  # the number of randomizations to perform
    include_canonical_smiles: bool = False,  # whether to include the canonical SMILES when using the augmentation
):
    prompts = []

    if not smiles_augmentation:
        smiles_augmentation_rounds = 1
    for _ in range(smiles_augmentation_rounds):
        target_name = target
        for key, value in target_rename_dict.items():
            target_name = target_name.replace(key, value)

        for _, row in df.iterrows():
            if encode_value:
                value = encode_categorical_value(
                    row[target], encoding_dict=encoding_dict
                )
            else:
                value = row[target]

            repr = row[representation_col]
            if smiles_augmentation:
                repr = randomize_smiles(repr, random_type=smiles_augmentation_type)
            prompts.append(
                {
                    "prompt": prompt_prefix
                    + ONE_PROPERTY_FORWARD_PROMPT_TEMPLATE.format(
                        property=target_name, text=repr
                    ),
                    "completion": ONE_PROPERTY_FORWARD_COMPLETION_TEMPLATE.format(
                        value=value
                    ),
                    "repr": row[representation_col],
                    "this_repr": repr,
                }
            )
    if smiles_augmentation and include_canonical_smiles:
        for _, row in df.iterrows():
            if encode_value:
                value = encode_categorical_value(
                    row[target], encoding_dict=encoding_dict
                )
            else:
                value = row[target]

            repr = row[representation_col]
            prompts.append(
                {
                    "prompt": prompt_prefix
                    + ONE_PROPERTY_FORWARD_PROMPT_TEMPLATE.format(
                        property=target_name, text=repr
                    ),
                    "completion": ONE_PROPERTY_FORWARD_COMPLETION_TEMPLATE.format(
                        value=value
                    ),
                    "repr": repr,
                    "this_repr": repr,
                }
            )

    df = pd.DataFrame(prompts)
    df.dropna(subset=["prompt"], inplace=True)
    df = df.sample(frac=1).reset_index(drop=True) # shuffle
    return df


# %% ../notebooks/03_input.ipynb 21
def create_single_property_forward_prompts_regression(
    df,  # input data
    target,  # target property
    target_rename_dict,  # dict to rename target property from the column name in df to the target property name in the prompt
    prompt_prefix="",  # prefix to add to the prompt, e.g. "I am an expert chemist"
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


# %% ../notebooks/03_input.ipynb 25
POLYMER_ONE_PROPERTY_INVERSE_PROMPT_TEMPLATE_CAT = (
    "what is a polymer with {class_name} {property}?###"
)
POLYMER_ONE_PROPERTY_INVERSE_COMPLETION_TEMPLATE_CAT = " {text}@@@"

POLYMER_ONE_PROPERTY_INVERSE_PROMPT_TEMPLATE_CAT_W_COMPOSITION = "what is a polymer with {class_name} {property} and {num_A} A, {num_B} B, {num_W} W, and {num_R} R?###"


# %% ../notebooks/03_input.ipynb 26
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


# %% ../notebooks/03_input.ipynb 27
def create_single_property_inverse_polymer_prompts(df, target, target_rename_dict, encode_value=True, with_composition=True):
    prompts = []

    target_name = target
    for key, value in target_rename_dict.items():
        target_name = target_name.replace(key, value)

    for _, row in df.iterrows():
        if encode_value:
            value = encode_categorical_value(row[target])
        else:
            value = row[target]

        if with_composition:
            comp_dict = get_polymer_composition_dict(row)

            prompt = POLYMER_ONE_PROPERTY_INVERSE_PROMPT_TEMPLATE_CAT_W_COMPOSITION.format(
                class_name=value, property=target_name, **comp_dict
            )
        else:
            prompt = (
                POLYMER_ONE_PROPERTY_INVERSE_PROMPT_TEMPLATE_CAT.format(
                    class_name=value, property=target_name
                ),
            )
        prompts.append(
            {
                "prompt": prompt,
                "completion": POLYMER_ONE_PROPERTY_INVERSE_COMPLETION_TEMPLATE_CAT.format(
                    text=row["string"]
                ),
            }
        )

    return pd.DataFrame(prompts)


# %% ../notebooks/03_input.ipynb 31
PROMPT_TEMPLATE_photoswitch_w_n_pistar = "What is a molecule with a pi-pi* transition wavelength of {} nm and n-pi* transition wavelength of {} nm###"
PROMPT_TEMPLATE_photoswitch_ = (
    "What is a molecule with a pi-pi* transition wavelength of {} nm###"
)
COMPLETION_TEMPLATE_photoswitch_ = "{}@@@"


def generate_inverse_photoswitch_prompts(data: pd.DataFrame) -> pd.DataFrame:
    prompts = []
    completions = []

    for i, row in data.iterrows():
        if np.isnan(row["E isomer n-pi* wavelength in nm"]):
            prompt = PROMPT_TEMPLATE_photoswitch_.format(
                row["E isomer pi-pi* wavelength in nm"]
            )
        else:
            prompt = PROMPT_TEMPLATE_photoswitch_w_n_pistar.format(
                row["E isomer pi-pi* wavelength in nm"],
                row["E isomer n-pi* wavelength in nm"],
            )

        completion = COMPLETION_TEMPLATE_photoswitch_.format(row["SMILES"])
        prompts.append(prompt)
        completions.append(completion)

    prompts = pd.DataFrame({"prompt": prompts, "completion": completions})

    return prompts


# %% ../notebooks/03_input.ipynb 49
def generate_property_desc(properties, gas_data, gas): 
    if properties is None: 
        return ""
    text = []
    row = gas_data[gas_data["formula"] == gas]
    for prop in properties:
        text.append(f"{prop.replace('_', ' ')} {row[prop].values[0]}")
    
    text = ", ".join(text)
    
    return f"({text})"



# %% ../notebooks/03_input.ipynb 51
_GAS_CONTEXT_PROMPT_TEMPLATE = "What is the {identifier} {description} Henry cofficient of {repr}###"


def create_prompts_w_gas_context(
    df, gas_data, gases=["CO2", "Xe"], properties=None, identifier=None, regression=False, representation="info.mofid.mofid_clean"
):
    prompts = []

    identifier = "formula" if identifier is None else identifier

    for _, row in df.iterrows():
        for gas in gases:
            subset = gas_data[gas_data["formula"] == gas]
          
            name = subset[identifier].values[0].replace("_", " ")
            if not regression:
                column = subset["related_column"].values[0]
            else:
                raise NotImplementedError("Regression not implemented yet")
            if not pd.isna(row[column]) and not 'nan' in row[column]:
                if properties is None:
                    property_desc = ""
                else:
                    property_desc = generate_property_desc(properties, gas_data, gas)

                prompts.append(
                    {
                        "prompt": _GAS_CONTEXT_PROMPT_TEMPLATE.format(
                            identifier=name,
                            description=property_desc,
                            repr=row[representation],
                        ),
                        "completion": f"{row[column]}@@@",
                        "repr": row[representation],
                    }
                )

    df = pd.DataFrame(prompts)
    df.dropna(subset=["prompt"], inplace=True)
    df = df.sample(frac=1).reset_index(drop=True)  # shuffle

    return pd.DataFrame(prompts)

# %% ../notebooks/03_input.ipynb 58
def create_mof_yield_prompt(row): 
    linkers = row[['linker_1', 'linker_2']]
    linkers = [l for l in linkers if not pd.isna(l)]

    metals = row['core_All_Metals'].split(',')

    solvents = row[['solvent1', 'solvent2', 'solvent3', 'solvent4', 'solvent5']]
    solvents = [s for s in solvents if not pd.isna(s)]
    sol_molratio = row[['sol_molratio1', 'sol_molratio2', 'sol_molratio3', 'sol_molratio4', 'sol_molratio5']]
    sol_molratio = [s for s in sol_molratio if not pd.isna(s)]
    additives = row[['additive1', 'additive2', 'additive3', 'additive4', 'additive5']]
    additives = [a for a in additives if not pd.isna(a)]

    temperature = row['temperature_Celsius']
    time = row['time_h']

    start = 'What is the yield of the reaction of the metal' 
    if len(metals) > 1:
        start += 's '
    else: 
        start += ' '

    start += ', '.join(metals) + ' with the linker' 
    if len(linkers) > 1:
        start += 's '
    else:
        start += ' '
    
    start += ', '.join(linkers) 
    
    # for the solvents, combine their names and molratios
    solvents = [f"{np.round(r,2)} {s}" for s, r in zip(solvents, sol_molratio)]

    start += ' in the solvents ' + ', '.join(solvents) + f' at {temperature} Celsius for {time} hours'

    # add the additives
    if len(additives) > 0:
        start += ' with the additive' 
        if len(additives) > 1:
            start += 's '
        else:
            start += ' '
        start += ', '.join(additives) + '?'
    else:
        start += '?'
        
    return start
    

# %% ../notebooks/03_input.ipynb 62
def get_mof_yield_prompt_completions(dataframe, yield_column: str = "yield"): 
    rows = []

    for i, row in dataframe.iterrows(): 
        prompt = create_mof_yield_prompt(row)
        completion = f"{int(row[yield_column])}@@@"
        rows.append({
            'prompt': prompt,
            'completion': completion,
            'repr': row['basename']
        })
    
    return pd.DataFrame(rows)
