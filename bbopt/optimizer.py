#!/usr/bin/env python
# -*- coding: utf-8 -*-
# __coconut_hash__ = 0x99975b18

# Compiled with Coconut version 1.4.0-post_dev23 [Ernest Scribbler]

"""
The main BBopt interface.
"""

# Coconut Header: -------------------------------------------------------------

from __future__ import print_function, absolute_import, unicode_literals, division
import sys as _coconut_sys, os.path as _coconut_os_path
_coconut_file_path = _coconut_os_path.dirname(_coconut_os_path.abspath(__file__))
_coconut_cached_module = _coconut_sys.modules.get(str("__coconut__"))
if _coconut_cached_module is not None and _coconut_os_path.dirname(_coconut_cached_module.__file__) != _coconut_file_path:
    del _coconut_sys.modules[str("__coconut__")]
_coconut_sys.path.insert(0, _coconut_file_path)
from __coconut__ import _coconut, _coconut_MatchError, _coconut_igetitem, _coconut_base_compose, _coconut_forward_compose, _coconut_back_compose, _coconut_forward_star_compose, _coconut_back_star_compose, _coconut_forward_dubstar_compose, _coconut_back_dubstar_compose, _coconut_pipe, _coconut_back_pipe, _coconut_star_pipe, _coconut_back_star_pipe, _coconut_dubstar_pipe, _coconut_back_dubstar_pipe, _coconut_bool_and, _coconut_bool_or, _coconut_none_coalesce, _coconut_minus, _coconut_map, _coconut_partial, _coconut_get_function_match_error, _coconut_addpattern, _coconut_sentinel
from __coconut__ import *
if _coconut_sys.version_info >= (3,):
    _coconut_sys.path.pop(0)

# Compiled Coconut: -----------------------------------------------------------



import os
import json
if _coconut_sys.version_info < (3,):
    import cPickle as pickle
else:
    import pickle
import math
import itertools
import time

import numpy as np
from portalocker import Lock

from bbopt.registry import backend_registry
from bbopt.registry import init_backend
from bbopt.registry import alg_registry
from bbopt.params import param_processor
from bbopt.util import Str
from bbopt.util import norm_path
from bbopt.util import json_serialize
from bbopt.util import best_example
from bbopt.util import sync_file
from bbopt.util import ensure_file
from bbopt.util import clear_file
from bbopt.util import denumpy_all
from bbopt.constants import data_file_ext
from bbopt.constants import lock_timeout
from bbopt.constants import default_alg
from bbopt.constants import default_protocol


class BlackBoxOptimizer(_coconut.object):
    """Main bbopt optimizer object. See https://github.com/evhub/bbopt for documentation."""

    def __init__(self, file, protocol=None):
        """Construct a new BlackBoxOptimizer. It is recommended to pass file=__file__."""
        if not isinstance(file, Str):
            raise TypeError("file must be a string")
        self._file = norm_path(file)

        if protocol is None:
# auto-detect protocol
            self._protocol = "json"
            if not os.path.exists(self.data_file):
                self._protocol = default_protocol
        else:
            self._protocol = protocol

        self.reload()

    def reload(self):
        """Completely reload the optimizer."""
        self._old_params = {}
        self._examples = []
        self._load_data()
        self.run(alg=None)  # backend is set to serving by default

    @property
    def _use_json(self):
        """Whether we are currently saving in json or pickle."""
        return self._protocol == "json"

    def _loads(self, raw_contents):
        """Load data from the given raw data string."""
        if self._use_json:
            return json.loads(str(raw_contents, encoding="utf-8"))
        else:
            return pickle.loads(raw_contents)

    def _dumps(self, unserialized_data):
        """Dump data to a raw data string."""
        if self._use_json:
            return json.dumps((json_serialize)(unserialized_data)).encode(encoding="utf-8")
        else:
            return pickle.dumps(unserialized_data, protocol=self._protocol)

    def run_backend(self, backend, *args, **options):
        """Optimize parameters using the given backend."""
        self.backend = init_backend(backend, self._examples, self._old_params, *args, **options)
        self._new_params = {}
        self._current_example = {"values": {}}

    @property
    def algs(self):
        """All algorithms supported by run."""
        return alg_registry.asdict()

    def run(self, alg=default_alg):
        """Optimize parameters using the given algorithm
        (use .algs to get the list of valid algorithms)."""
        backend, options = alg_registry[alg]
        self.run_backend(backend, **options)

    @property
    def _got_reward(self):
        """Whether we have seen a maximize/minimize call yet."""
        return "loss" in self._current_example or "gain" in self._current_example

    def _param(self, name, func, *args, **kwargs):
        """Create a black box parameter and return its value."""
        if self._got_reward:
            raise ValueError("all parameter definitions must come before maximize/minimize")
        if not isinstance(name, Str):
            raise TypeError("name must be a string, not {_coconut_format_0}".format(_coconut_format_0=(name)))
        if name in self._new_params:
            raise ValueError("parameter of name {_coconut_format_0} already exists".format(_coconut_format_0=(name)))

        args = param_processor.standardize_args(func, args)
        kwargs = param_processor.standardize_kwargs(kwargs)

        value = self.backend.param(name, func, *args, **kwargs)
        self._new_params[name] = (func, args, kwargs)
        self._current_example["values"][name] = value
        return value

    def remember(self, info):
        """Store a dictionary of information about the current run."""
        if self._got_reward:
            raise ValueError("remember calls must come before maximize/minimize")
        self._current_example.setdefault("memo", {}).update(info)

    def minimize(self, value):
        """Set the loss of the current run."""
        self._set_reward("loss", value)

    def maximize(self, value):
        """Set the gain of the current run."""
        self._set_reward("gain", value)

    @property
    def is_serving(self):
        """Whether we are currently using the serving backend or not."""
        return isinstance(self.backend, backend_registry[None])

    def _set_reward(self, reward_type, value):
        """Set the gain or loss to the given value."""
        if self._got_reward:
            raise ValueError("only one call to maximize or minimize is allowed")
        if isinstance(value, np.ndarray):
            if len(value.shape) != 1:
                raise ValueError("gain/loss must be a scalar or 1-dimensional array, not {_coconut_format_0}".format(_coconut_format_0=(value)))
            value = tuple(value)
        self._current_example[reward_type] = denumpy_all(value)
        if not self.is_serving:
            self._save_data()

    @property
    def data_file(self):
        """The path to the file we are saving data to."""
        return os.path.splitext(self._file)[0] + data_file_ext + (".json" if self._use_json else ".pickle")

    def tell_examples(self, examples):
        """Load the given examples into memory."""
        for ex in examples:
            if ex not in self._examples:
                self._examples.append(ex)

    def _load_from(self, df):
        """Load data from the given file."""
        contents = df.read()
        if contents:
            _coconut_match_to = self._loads(contents)
            _coconut_match_check = False
            if (_coconut.isinstance(_coconut_match_to, _coconut.abc.Mapping)) and (_coconut.len(_coconut_match_to) == 2):
                _coconut_match_temp_0 = _coconut_match_to.get("params", _coconut_sentinel)
                _coconut_match_temp_1 = _coconut_match_to.get("examples", _coconut_sentinel)
                if (_coconut_match_temp_0 is not _coconut_sentinel) and (_coconut_match_temp_1 is not _coconut_sentinel):
                    params = _coconut_match_temp_0
                    examples = _coconut_match_temp_1
                    _coconut_match_check = True
            if not _coconut_match_check:
                _coconut_match_val_repr = _coconut.repr(_coconut_match_to)
                _coconut_match_err = _coconut_MatchError("pattern-matching failed for " '\'{"params": params, "examples": examples} = self._loads(contents)\'' " in " + (_coconut_match_val_repr if _coconut.len(_coconut_match_val_repr) <= 500 else _coconut_match_val_repr[:500] + "..."))
                _coconut_match_err.pattern = '{"params": params, "examples": examples} = self._loads(contents)'
                _coconut_match_err.value = _coconut_match_to
                raise _coconut_match_err

            self._old_params = params
            self.tell_examples(examples)

    def _load_data(self):
        """Load examples from data file."""
        ensure_file(self.data_file)
        with Lock(self.data_file, "rb", timeout=lock_timeout) as df:
            self._load_from(df)

    def get_data(self):
        """Get all currently-loaded data as a dictionary containing params and examples."""
        self._old_params.update(self._new_params)
        return {"params": self._old_params, "examples": self._examples}

    @property
    def num_examples(self):
        """The number of examples seen so far (current example not counted until maximize/minimize call)."""
        return len(self._examples)

    def _save_data(self):
        """Save examples to data file."""
        assert "timestamp" not in self._current_example, "multiple _save_data calls on _current_example = {_coconut_format_0}".format(_coconut_format_0=(self._current_example))
        with Lock(self.data_file, "rb+", timeout=lock_timeout) as df:
# we create the timestamp while we have the lock to ensure its uniqueness
            self._current_example["timestamp"] = time.time()
            self.tell_examples([self._current_example])
            self._load_from(df)
            clear_file(df)
            ((df.write)((self._dumps)(self.get_data())))
            sync_file(df)

    def get_current_run(self):
        """Return a dictionary containing the current parameters and reward."""
        try:
            return self._current_example
        except AttributeError:
            raise ValueError("get_current_run calls must come after run")

    def get_optimal_run(self):
        """Return a dictionary containing the optimal parameters and reward computed so far."""
        return best_example(self._examples)

# Base random functions:

    def randrange(self, name, *args, **kwargs):
        """Create a new parameter with the given name modeled by random.randrange(*args)."""
        return self._param(name, "randrange", *args, **kwargs)

    def choice(self, name, seq, **kwargs):
        """Create a new parameter with the given name modeled by random.choice(seq)."""
        return self._param(name, "choice", seq, **kwargs)

    def uniform(self, name, a, b, **kwargs):
        """Create a new parameter with the given name modeled by random.uniform(a, b)."""
        return self._param(name, "uniform", a, b, **kwargs)

    def triangular(self, name, low, high, mode, **kwargs):
        """Create a new parameter with the given name modeled by random.triangular(low, high, mode)."""
        return self._param(name, "triangular", low, high, mode, **kwargs)

    def betavariate(self, name, alpha, beta, **kwargs):
        """Create a new parameter with the given name modeled by random.betavariate(alpha, beta)."""
        return self._param(name, "betavariate", alpha, beta, **kwargs)

    def expovariate(self, name, lambd, **kwargs):
        """Create a new parameter with the given name modeled by random.expovariate(lambd)."""
        return self._param(name, "expovariate", lambd, **kwargs)

    def gammavariate(self, name, alpha, beta, **kwargs):
        """Create a new parameter with the given name modeled by random.gammavariate(alpha, beta)."""
        return self._param(name, "gammavariate", alpha, beta, **kwargs)

    def normalvariate(self, name, mu, sigma, **kwargs):
        """Create a new parameter with the given name modeled by random.gauss(mu, sigma)."""
        return self._param(name, "normalvariate", mu, sigma, **kwargs)

    def vonmisesvariate(self, name, kappa, **kwargs):
        """Create a new parameter with the given name modeled by random.vonmisesvariate(kappa)."""
        return self._param(name, "vonmisesvariate", kappa, **kwargs)

    def paretovariate(self, name, alpha, **kwargs):
        """Create a new parameter with the given name modeled by random.paretovariate(alpha)."""
        return self._param(name, "paretovariate", alpha, **kwargs)

    def weibullvariate(self, name, alpha, beta, **kwargs):
        """Create a new parameter with the given name modeled by random.weibullvariate(alpha, beta)."""
        return self._param(name, "weibullvariate", alpha, beta, **kwargs)

# Derived random functions:

    def randint(self, name, a, b, **kwargs):
        """Create a new parameter with the given name modeled by random.randint(a, b)."""
        start, stop = a, b - 1
        return self.randrange(name, start, stop, **kwargs)

    def random(self, name, **kwargs):
        """Create a new parameter with the given name modeled by random.random()."""
        return self.uniform(name, 0, 1, **kwargs)

    def getrandbits(self, name, k, **kwargs):
        """Create a new parameter with the given name modeled by random.getrandbits(k)."""
        stop = 2**k
        return self.randrange(name, stop, **kwargs)

    gauss = normalvariate

    def loguniform(self, name, min_val, max_val, **kwargs):
        """Create a new parameter with the given name modeled by
        math.exp(random.uniform(math.log(min_val), math.log(max_val)))."""
        kwargs = (_coconut.functools.partial(param_processor.modify_kwargs, math.log))(kwargs)
        log_a, log_b = math.log(min_val), math.log(max_val)
        return math.exp(self.uniform(name, log_a, log_b, **kwargs))

    def lognormvariate(self, name, mu, sigma, **kwargs):
        """Create a new parameter with the given name modeled by random.lognormvariate(mu, sigma)."""
        kwargs = (_coconut.functools.partial(param_processor.modify_kwargs, math.log))(kwargs)
        return math.exp(self.normalvariate(name, mu, sigma, **kwargs))

    def randbool(self, name, **kwargs):
        """Create a new boolean parameter with the given name."""
        return self.choice(name, [False, True], **kwargs)

    def sample(self, name, population, k, **kwargs):
        """Create a new parameter with the given name modeled by random.sample(population, k)."""
        if not isinstance(name, Str):
            raise TypeError("name must be string, not {_coconut_format_0}".format(_coconut_format_0=(name)))
        sampling_population = [x for x in population]
        sample = []
        for i in range(k):
            if len(sampling_population) <= 1:
                sample.append(sampling_population[0])
            else:
                def _coconut_lambda_0(val):
                    elem = _coconut_igetitem(val, i)
                    return sampling_population.index(elem) if elem in sampling_population else 0
                proc_kwargs = param_processor.modify_kwargs(_coconut_lambda_0, kwargs)
                ind = self.randrange("{_coconut_format_0}[{_coconut_format_1}]".format(_coconut_format_0=(name), _coconut_format_1=(i)), len(sampling_population), **proc_kwargs)
                sample.append(sampling_population.pop(ind))
        return sample

    def shuffle(self, name, x, **kwargs):
        """Create a new parameter with the given name modeled by random.shuffle(x)."""
        return self.sample(name, x, len(x), **kwargs)

# Array-based random functions:

    def _array_param(self, func, name, shape, kwargs):
        """Create a new array parameter for the given name and shape with entries from func."""
        if not isinstance(name, Str):
            raise TypeError("name must be string, not {_coconut_format_0}".format(_coconut_format_0=(name)))
        arr = np.zeros(shape)
        for indices in itertools.product(*map(range, shape)):
            index_str = ",".join(map(str, indices))
            cell_name = "{_coconut_format_0}[{_coconut_format_1}]".format(_coconut_format_0=(name), _coconut_format_1=(index_str))
            proc_kwargs = param_processor.modify_kwargs(lambda _=None: _[indices], kwargs)
            arr[indices] = func(cell_name, **proc_kwargs)
        return arr

    def rand(self, name, *shape, **kwargs):
        """Create a new array parameter for the given name and shape modeled by np.random.rand."""
        return self._array_param(self.random, name, shape, kwargs)

    def randn(self, name, *shape, **kwargs):
        """Create a new array parameter for the given name and shape modeled by np.random.randn."""
        return self._array_param(_coconut_partial(self.normalvariate, {1: 0, 2: 1}, 3), name, shape, kwargs)
