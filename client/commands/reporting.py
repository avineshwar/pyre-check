# Copyright (c) 2016-present, Facebook, Inc.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

# pyre-strict

import argparse
import fnmatch
import json
import logging
import os
from typing import Any, Dict, Iterable, List, Set  # noqa

from .. import log
from ..configuration import Configuration
from ..error import Error
from ..filesystem import AnalysisDirectory
from .command import ClientException, Command, Result


LOG = logging.getLogger(__name__)  # type: logging.Logger

TEXT = "text"  # type: str
JSON = "json"  # type: str


class Reporting(Command):
    def __init__(
        self,
        arguments: argparse.Namespace,
        configuration: Configuration,
        analysis_directory: AnalysisDirectory,
    ) -> None:
        super().__init__(arguments, configuration, analysis_directory)
        self._verbose = arguments.verbose  # type: bool
        self._output = arguments.output  # type: str
        self._ignore_all_errors_paths = (
            configuration.ignore_all_errors
        )  # type: Iterable[str]

    def _print(self, errors: Iterable[Error]) -> None:
        errors = [
            error
            for error in errors
            if (
                not error.is_ignored()
                and (self._verbose or not (error.is_external_to_global_root()))
            )
        ]
        errors = sorted(
            errors, key=lambda error: (error.path, error.line, error.column)
        )

        if errors:
            length = len(errors)
            LOG.error("Found %d type error%s!", length, "s" if length > 1 else "")
        else:
            LOG.log(log.SUCCESS, "No type errors found")

        if self._output == TEXT:
            log.stdout.write("\n".join([repr(error) for error in errors]))
        else:
            log.stdout.write(json.dumps([error.__dict__ for error in errors]))

    def _get_directories_to_analyze(self) -> Set[str]:
        current_project_directory = self._analysis_directory.get_filter_root()
        directories_to_analyze = {
            os.path.relpath(filter_root, os.getcwd())
            for filter_root in current_project_directory
        }
        return directories_to_analyze

    def _get_errors(self, result: Result) -> Set[Error]:
        result.check()

        errors = set()
        # pyre-ignore: T39175181
        results = {}  # type: List[Dict[str, Any]]
        try:
            results = json.loads(result.output)
        except (json.JSONDecodeError, ValueError):
            raise ClientException("Invalid output: `{}`.".format(result.output))

        for error in results:
            full_path = os.path.realpath(
                os.path.join(self._analysis_directory.get_root(), error["path"])
            )
            # Relativize path to user's cwd.
            relative_path = self._relative_path(full_path)
            error["path"] = relative_path
            ignore_error = False
            external_to_global_root = True
            if full_path.startswith(self._current_directory):
                external_to_global_root = False
            for absolute_ignore_path in self._ignore_all_errors_paths:
                if fnmatch.fnmatch(full_path, (absolute_ignore_path + "*")):
                    ignore_error = True
                    break
            errors.add(Error(ignore_error, external_to_global_root, **error))

        return errors
