from __future__ import print_function, division, absolute_import

from collections import Iterable
from six import iteritems, string_types
import numpy as np

from openmdao.utils.options_dictionary import OptionsDictionary


class ODEFunction(object):
    """
    Define an ODE of the form y' = f(t, x, y).

    Attributes
    ----------
    _system_class : System
        OpenMDAO Group or Component class defining our ODE.
    _system_init_kwargs : dict
        Dictionary of kwargs that should be passed in when instantiating system_class.
    _time_options : OptionsDictionary
        Options for the time or time-like variable.
    _states : dict of OptionsDictionary
        Dictionary of options dictionaries for each state.
    _parameters : dict of OptionsDictionary
        Dictionary of options dictionaries for each parameter.
    """

    def __init__(self, **kwargs):
        """
        Initialize class attributes.

        Parameters
        ----------
        kwargs : dict
            Keyword arguments that will be passed to the initialize method.
        """
        self._system_class = None
        self._system_init_kwargs = {}

        time_options = OptionsDictionary()
        time_options.declare('paths', default=[], type_=Iterable)
        time_options.declare('units', default=None, type_=(string_types, type(None)))

        self._time_options = time_options
        self._states = {}
        self._parameters = {}

        self.initialize(**kwargs)

    def initialize(self, **kwargs):
        """
        Optional method that calls declare_time, declare_state, and/or declare_parameter.

        Parameters
        ----------
        kwargs : dict
            Keyword arguments passed in during instantiation.
        """
        pass

    def set_system(self, system_class, system_init_kwargs=None):
        """
        Set the OpenMDAO System that computes the ODE function.

        Parameters
        ----------
        system_class : System
            OpenMDAO Group or Component class defining our ODE.
        system_init_kwargs : dict or None
            Dictionary of kwargs that should be passed in when instantiating system_class.
        """
        self._system_class = system_class
        if system_init_kwargs is not None:
            self._system_init_kwargs = system_init_kwargs

    def declare_time(self, paths=None, units=None):
        """
        Specify the paths and units of time or the time-like variable.

        Parameters
        ----------
        paths : string_types or Iterable or None
            Targets for the time or time-like variable within the ODE, or None if no models
            are explicitly time-dependent. Default is None.
        units : str or None
            Units for the integration variable within the ODE. Default is None.
        """
        if isinstance(paths, string_types):
            self._time_options['paths'] = [paths]
        elif isinstance(paths, Iterable):
            self._time_options['paths'] = paths
        elif paths is not None:
            raise ValueError('paths must be of type string_types or Iterable or None')
        if units is not None:
            self._time_options['units'] = units

    def declare_state(self, name, rate_path, paths=None, shape=None, units=None):
        """
        Add an ODE state variable.

        Parameters
        ----------
        name : str
            The name of the state variable as seen by the driver. This variable will
            exist as an interface to the ODE.
        rate_path : str
            The path to the variable within the ODE which represents the derivative of
            the state variable w.r.t. the variable of integration.
        paths : string_types or Iterable or None
            Paths to inputs in the ODE to which the incoming value of the state variable
            needs to be connected.
        shape : int or tuple or None
            The shape of the variable to potentially be provided as a control.
        units : str or None
            Units of the variable.
        """
        if name in self._states:
            raise ValueError('State {0} has already been declared.'.format(name))

        options = OptionsDictionary()
        options.declare('name', type_=string_types)
        options.declare('rate_path', type_=string_types)
        options.declare('paths', default=[], type_=Iterable)
        options.declare('shape', default=(1,), type_=tuple)
        options.declare('units', default=None, type_=string_types)

        options['name'] = name
        options['rate_path'] = rate_path
        if isinstance(paths, string_types):
            options['paths'] = [paths]
        elif isinstance(paths, Iterable):
            options['paths'] = paths
        elif paths is not None:
            raise ValueError('paths must be of type string_types or Iterable or None')
        if np.isscalar(shape):
            options['shape'] = (shape,)
        elif isinstance(shape, Iterable):
            options['shape'] = tuple(shape)
        elif shape is not None:
            raise ValueError('shape must be of type int or Iterable or None')
        if units is not None:
            options['units'] = units

        self._states[name] = options

    def declare_parameter(self, name, paths, shape=None, units=None):
        """
        Declare an input to the ODE.

        Parameters
        ----------
        name : str
            The name of the state variable as seen by the driver. This variable will
            exist as an interface to the ODE.
        paths : string_types or Iterable or None
            Paths to inputs in the ODE to which the incoming value of the state variable
            needs to be connected.
        shape : int or tuple or None
            Shape of the parameter.
        units : str or None
            Units of the parameter.
        """
        if name in self._parameters:
            raise ValueError('Parameter {0} has already been declared.'.format(name))

        options = OptionsDictionary()
        options.declare('name', type_=string_types)
        options.declare('paths', default=[], type_=Iterable)
        options.declare('shape', default=(1,), type_=tuple)
        options.declare('units', default=None, type_=string_types)

        options['name'] = name
        options['paths'] = paths
        if np.isscalar(shape):
            options['shape'] = (shape,)
        elif isinstance(shape, Iterable):
            options['shape'] = tuple(shape)
        elif shape is not None:
            raise ValueError('shape must be of type int or Iterable or None')
        if units is not None:
            options['units'] = units

        self._parameters[name] = options