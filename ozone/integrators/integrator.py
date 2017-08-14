from __future__ import division

import numpy as np
from openmdao.api import Group, IndepVarComp
from six import iteritems

import ozone.schemes.scheme as schemes
from ozone.components.time_comp import TimeComp
from ozone.components.starting_comp import StartingComp
from ozone.components.parameter_comp import ParameterComp
from ozone.schemes.scheme import GLMScheme
from ozone.schemes.runge_kutta import RK4
from ozone.ode_function import ODEFunction
from ozone.utils.var_names import get_name
from ozone.utils.misc import get_scheme


class Integrator(Group):
    """
    The base class for all integration schemes.
    """

    def initialize(self):
        self.metadata.declare('ode_function', type_=ODEFunction, required=True)
        self.metadata.declare('scheme', default=RK4(), type_=GLMScheme)
        self.metadata.declare('starting_coeffs', type_=(np.ndarray, type(None)))

        self.metadata.declare('initial_conditions', type_=(dict, type(None)))
        self.metadata.declare('parameters', type_=(dict, type(None)))
        self.metadata.declare('initial_time')
        self.metadata.declare('final_time')
        self.metadata.declare('normalized_times', type_=np.ndarray, required=True)
        self.metadata.declare('all_norm_times', type_=np.ndarray, required=True)

    def setup(self):
        ode_function = self.metadata['ode_function']
        scheme = self.metadata['scheme']
        starting_coeffs = self.metadata['starting_coeffs']

        initial_conditions = self.metadata['initial_conditions']
        given_parameters = self.metadata['parameters']
        initial_time = self.metadata['initial_time']
        final_time = self.metadata['final_time']

        num_step_vars = scheme.num_values

        has_starting_method = scheme.starting_method is not None
        is_starting_method = starting_coeffs is not None

        states = ode_function._states
        parameters = ode_function._parameters
        time_units = ode_function._time_options['units']

        starting_norm_times, my_norm_times = self._get_meta()
        stage_norm_times = self._get_stage_norm_times()
        all_norm_times = self.metadata['all_norm_times']

        # ------------------------------------------------------------------------------------
        # Check starting_coeffs
        if is_starting_method:
            # (num_starting, num_time_steps, num_step_vars,)
            assert len(starting_coeffs.shape) == 3, \
                'starting_coeffs must be a rank-3 array, but its rank is %i' \
                % len(starting_coeffs.shape)
            assert starting_coeffs.shape[1:] == (len(my_norm_times), scheme.num_values), \
                'starting_coeffs must have shape (num_starting, num_time_steps, num_step_vars,).' \
                + 'It has shape %i x %i x %i, but it should have shape (? x %i x %i)' % (
                    starting_coeffs.shape[0], starting_coeffs.shape[1], starting_coeffs.shape[2],
                    len(my_norm_times), scheme.num_values
                )

        # ------------------------------------------------------------------------------------
        # inputs
        if initial_conditions is not None or given_parameters is not None \
                or initial_time is not None or final_time is not None:
            comp = IndepVarComp()
            promotes = []

        # Initial conditions
        if initial_conditions is not None:
            for state_name, value in iteritems(initial_conditions):
                name = get_name('IC', state_name)
                state = ode_function._states[state_name]

                comp.add_output(name, val=value, units=state['units'])
                promotes.append(name)

        # Given parameters
        if given_parameters is not None:
            for parameter_name, value in iteritems(given_parameters):
                name = get_name('parameter', parameter_name)
                parameter = ode_function._parameters[parameter_name]

                comp.add_output(name, val=value, units=parameter['units'])
                promotes.append(name)

        # Initial time
        if initial_time is not None:
            comp.add_output('initial_time', val=initial_time, units=time_units)
            promotes.append('initial_time')

        # Final time
        if final_time is not None:
            comp.add_output('final_time', val=final_time, units=time_units)
            promotes.append('final_time')

        if initial_conditions is not None or given_parameters is not None \
                or initial_time is not None or final_time is not None:
            self.add_subsystem('inputs', comp, promotes_outputs=promotes)

        # ------------------------------------------------------------------------------------
        # Time comp
        comp = TimeComp(time_units=time_units,
            normalized_times=my_norm_times, stage_norm_times=stage_norm_times)
        self.add_subsystem('time_comp', comp, promotes_inputs=['initial_time', 'final_time'])

        # ------------------------------------------------------------------------------------
        # Parameter comp
        if len(parameters) > 0:
            promotes = [
                (get_name('in', parameter_name), get_name('parameter', parameter_name))
                for parameter_name in parameters]
            self.add_subsystem('parameter_comp',
                ParameterComp(parameters=parameters,
                    normalized_times=all_norm_times, stage_norm_times=stage_norm_times),
                promotes_inputs=promotes)

        # ------------------------------------------------------------------------------------
        # Starting system
        promotes = []
        promotes.extend([get_name('IC', state_name) for state_name in states])

        if not has_starting_method:
            starting_system = StartingComp(states=states, num_step_vars=num_step_vars)
        else:
            starting_scheme_name, starting_coeffs, starting_time_steps = scheme.starting_method
            scheme = get_scheme(starting_scheme_name)

            starting_system = self.__class__(ode_function=ode_function, scheme=scheme,
                normalized_times=starting_norm_times, all_norm_times=all_norm_times,
                starting_coeffs=starting_coeffs,
            )

            promotes.extend([get_name('parameter', parameter_name) for parameter_name in parameters])
            promotes.append('initial_time')
            promotes.append('final_time')

        self.add_subsystem('starting_system', starting_system,
            promotes_inputs=promotes)

    def _get_state_names(self, comp, type_, i_step=None, i_stage=None, j_stage=None):
        return self._get_names('states',
            comp, type_, i_step=i_step, i_stage=i_stage, j_stage=j_stage)

    def _get_parameter_names(self, comp, type_, i_step=None, i_stage=None, j_stage=None):
        return self._get_names('parameters',
            comp, type_, i_step=i_step, i_stage=i_stage, j_stage=j_stage)

    def _get_names(self, variable_type, comp, type_, i_step=None, i_stage=None, j_stage=None):
        if variable_type == 'states':
            variables_dict = self.metadata['ode_function']._states
        elif variable_type == 'parameters':
            variables_dict = self.metadata['ode_function']._parameters

        names_list = []
        for variable_name, variable in iteritems(variables_dict):
            if type_ == 'rate_path':
                names = '{}.{}'.format(comp, variable['rate_path'])
            elif type_ == 'paths':
                names = ['{}.{}'.format(comp, tgt) for tgt in variable['paths']]
            else:
                names = '{}.{}'.format(comp, get_name(
                    type_, variable_name, i_step=i_step, i_stage=i_stage, j_stage=j_stage))

            names_list.append(names)

        return names_list

    def _connect_multiple(self, srcs_list, tgts_list, src_indices_list=None):
        if src_indices_list is None:
            for srcs, tgts in zip(srcs_list, tgts_list):
                self.connect(srcs, tgts)
        else:
            for srcs, tgts, src_indices in zip(srcs_list, tgts_list, src_indices_list):
                self.connect(srcs, tgts, src_indices=src_indices)

    def _create_ode(self, num):
        ode_function = self.metadata['ode_function']
        return ode_function._system_class(num=num, **ode_function._system_init_kwargs)

    def _get_meta(self):
        scheme = self.metadata['scheme']
        normalized_times = self.metadata['normalized_times']

        has_starting_method = scheme.starting_method is not None

        if has_starting_method:
            start_time_index = scheme.starting_method[2]
        else:
            start_time_index = 0

        # ode_function = self.metadata['ode_function']
        # states = ode_function._states
        # parameters = ode_function._parameters
        # time_units = ode_function._time_options['units']

        return normalized_times[:start_time_index+1], normalized_times[start_time_index:]

    def _get_scheme(self):
        scheme = self.metadata['scheme']

        return scheme.A, scheme.B, scheme.U, scheme.V, scheme.num_stages, scheme.num_values

    def _get_stage_norm_times(self):
        starting_norm_times, my_norm_times = self._get_meta()

        abscissa = self.metadata['scheme'].abscissa

        repeated_times1 = np.repeat(my_norm_times[:-1], len(abscissa))
        repeated_times2 = np.repeat(my_norm_times[1:], len(abscissa))
        tiled_abscissa = np.tile(abscissa, len(my_norm_times) - 1)

        stage_norm_times = repeated_times1 + (repeated_times2 - repeated_times1) * tiled_abscissa

        return stage_norm_times