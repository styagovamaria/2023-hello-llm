"""
Laboratory work.

Working with Large Language Models.
"""
# pylint: disable=too-few-public-methods, undefined-variable, too-many-arguments, super-init-not-called, duplicate-code
from collections import namedtuple
from pathlib import Path
from typing import Iterable, Sequence

from datasets import load_dataset
from torchinfo import summary
from transformers import BertForSequenceClassification, BertTokenizer

try:
    import torch
    from torch.utils.data.dataset import Dataset
except ImportError:
    print('Library "torch" not installed. Failed to import.')
    torch = namedtuple('torch', 'no_grad')(lambda: lambda fn: fn)  # type: ignore

import pandas as pd

from core_utils.llm.llm_pipeline import AbstractLLMPipeline
from core_utils.llm.metrics import Metrics
from core_utils.llm.raw_data_importer import AbstractRawDataImporter
from core_utils.llm.raw_data_preprocessor import AbstractRawDataPreprocessor, ColumnNames
from core_utils.llm.task_evaluator import AbstractTaskEvaluator
from core_utils.llm.time_decorator import report_time


class RawDataImporter(AbstractRawDataImporter):
    """
    A class that imports the HuggingFace dataset.
    """

    @report_time
    def obtain(self) -> None:
        """
        Download a dataset.

        Raises:
            TypeError: In case of downloaded dataset is not pd.DataFrame
        """
        self._raw_data = load_dataset(self._hf_name, split='train').to_pandas()


class RawDataPreprocessor(AbstractRawDataPreprocessor):
    """
    A class that analyzes and preprocesses a dataset.
    """

    def analyze(self) -> dict:
        """
        Analyze a dataset.

        Returns:
            dict: Dataset key properties
        """
        rows, cols = self._raw_data.shape
        data_droped_empty = self._raw_data.dropna()

        return {'dataset_number_of_samples': rows,
                'dataset_columns': cols,
                'dataset_duplicates': len(self._raw_data[self._raw_data.duplicated()]),
                'dataset_empty_rows': rows - len(data_droped_empty),
                'dataset_sample_min_len': min(data_droped_empty['toxic_comment'].str.len()),
                'dataset_sample_max_len': max(data_droped_empty['toxic_comment'].str.len())}

    @report_time
    def transform(self) -> None:
        """
        Apply preprocessing transformations to the raw dataset.
        """
        self._data = (
            self._raw_data.drop_duplicates()
            .rename(columns={'toxic_comment': ColumnNames.SOURCE.value,
                             'reasons': ColumnNames.TARGET.value})
        )
        self._data[ColumnNames.TARGET.value] = (
            self._data[ColumnNames.TARGET.value]
            .replace({'{"not_toxic":true}': '0', '{"toxic_content":true}': '1'})
        )
        self._data = (
            self._data[self._data[ColumnNames.TARGET.value].isin(['0', '1'])]
            .reset_index(drop=True)
        )


class TaskDataset(Dataset):
    """
    A class that converts pd.DataFrame to Dataset and works with it.
    """

    def __init__(self, data: pd.DataFrame) -> None:
        """
        Initialize an instance of TaskDataset.

        Args:
            data (pandas.DataFrame): Original data
        """
        self._data = data

    def __len__(self) -> int:
        """
        Return the number of items in the dataset.

        Returns:
            int: The number of items in the dataset
        """
        return len(self._data)

    def __getitem__(self, index: int) -> tuple[str, ...]:
        """
        Retrieve an item from the dataset by index.

        Args:
            index (int): Index of sample in dataset

        Returns:
            tuple[str, ...]: The item to be received
        """
        return (self._data.iloc[index][ColumnNames.SOURCE.value],)

    @property
    def data(self) -> pd.DataFrame:
        """
        Property with access to preprocessed DataFrame.

        Returns:
            pandas.DataFrame: Preprocessed DataFrame
        """
        return self._data


class LLMPipeline(AbstractLLMPipeline):
    """
    A class that initializes a model, analyzes its properties and infers it.
    """

    def __init__(
            self,
            model_name: str,
            dataset: TaskDataset,
            max_length: int,
            batch_size: int,
            device: str
    ) -> None:
        """
        Initialize an instance of LLMPipeline.

        Args:
            model_name (str): The name of the pre-trained model
            dataset (TaskDataset): The dataset used
            max_length (int): The maximum length of generated sequence
            batch_size (int): The size of the batch inside DataLoader
            device (str): The device for inference
        """
        super().__init__(model_name, dataset, max_length, batch_size, device)
        self._tokenizer = BertTokenizer.from_pretrained(model_name)
        self._model: torch.nn.Module = BertForSequenceClassification.from_pretrained(model_name)

    def analyze_model(self) -> dict:
        """
        Analyze model computing properties.

        Returns:
            dict: Properties of a model
        """
        config = self._model.config
        embeddings_length = config.max_position_embeddings
        ids = torch.ones(1, embeddings_length, dtype=torch.long)
        input_data = {
            'input_ids': ids,
            'attention_mask': ids
        }

        if not self._model:
            return {}

        model_stats = summary(
            self._model,
            input_data=input_data,
            device=self._device,
            verbose=0
        )
        return {
            "input_shape": {'attention_mask': list(model_stats.input_size['attention_mask']),
                            'input_ids': list(model_stats.input_size['input_ids'])},
            'embedding_size': embeddings_length,
            'output_shape': model_stats.summary_list[-1].output_size,
            'num_trainable_params': model_stats.trainable_params,
            'vocab_size': config.vocab_size,
            'size': model_stats.total_param_bytes,
            'max_context_length': config.max_length
        }

    @report_time
    def infer_sample(self, sample: tuple[str, ...]) -> str | None:
        """
        Infer model on a single sample.

        Args:
            sample (tuple[str, ...]): The given sample for inference with model

        Returns:
            str | None: A prediction
        """
        tokens = self._tokenizer(
                sample,
                max_length=self._max_length,
                padding=True,
                truncation=True,
                return_tensors='pt'
        )
        output = self._model(**tokens)
        return str(torch.argmax(output.logits).item())

    @report_time
    def infer_dataset(self) -> pd.DataFrame:
        """
        Infer model on a whole dataset.

        Returns:
            pd.DataFrame: Data with predictions
        """

    @torch.no_grad()
    def _infer_batch(self, sample_batch: Sequence[tuple[str, ...]]) -> list[str]:
        """
        Infer model on a single batch.

        Args:
            sample_batch (Sequence[tuple[str, ...]]): Batch to infer the model

        Returns:
            list[str]: Model predictions as strings
        """


class TaskEvaluator(AbstractTaskEvaluator):
    """
    A class that compares prediction quality using the specified metric.
    """

    def __init__(self, data_path: Path, metrics: Iterable[Metrics]) -> None:
        """
        Initialize an instance of Evaluator.

        Args:
            data_path (pathlib.Path): Path to predictions
            metrics (Iterable[Metrics]): List of metrics to check
        """

    @report_time
    def run(self) -> dict | None:
        """
        Evaluate the predictions against the references using the specified metric.

        Returns:
            dict | None: A dictionary containing information about the calculated metric
        """
