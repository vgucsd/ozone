import numpy as np
from six import iteritems

from openmdao.api import Group, IndepVarComp, NewtonSolver, DirectSolver, DenseJacobian

from ozone.integrators.integrator import Integrator
from ozone.components.vectorized_step_comp import VectorizedStepComp
from ozone.components.vectorized_stage_comp import VectorizedStageComp
from ozone.components.vectorized_output_comp import VectorizedOutputComp
from ozone.utils.var_names import get_name


class VectorizedIntegrator(Integrator):
    """
    Integrate an explicit scheme with a relaxed time-marching approach.
    """

    def initialize(self):
        super(VectorizedIntegrator, self).initialize()

        self.metadata.declare('formulation', default='MDF', values=['MDF', 'SAND'])

    def setup(self):
        super(VectorizedIntegrator, self).setup()

        ode_function = self.metadata['ode_function']
        scheme = self.metadata['scheme']
        starting_coeffs = self.metadata['starting_coeffs']
        formulation = self.metadata['formulation']

        has_starting_method = scheme.starting_method is not None
        is_starting_method = starting_coeffs is not None

        states = ode_function._states
        static_parameters = ode_function._static_parameters
        dynamic_parameters = ode_function._dynamic_parameters
        time_units = ode_function._time_options['units']

        starting_norm_times, my_norm_times = self._get_meta()

        glm_A, glm_B, glm_U, glm_V, num_stages, num_step_vars = self._get_scheme()

        num_time_steps = len(my_norm_times)

        # ------------------------------------------------------------------------------------

        integration_group = Group()
        self.add_subsystem('integration_group', integration_group)

        if formulation == 'SAND':
            comp = IndepVarComp()
            for state_name, state in iteritems(states):
                comp.add_output('Y:%s' % state_name,
                    shape=(num_time_steps - 1, num_stages,) + state['shape'],
                    units=state['units'])
                comp.add_design_var('Y:%s' % state_name)
            integration_group.add_subsystem('desvars_comp', comp)
        elif formulation == 'MDF':
            comp = IndepVarComp()
            for state_name, state in iteritems(states):
                comp.add_output('Y:%s' % state_name, val=0.,
                    shape=(num_time_steps - 1, num_stages,) + state['shape'],
                    units=state['units'])
            integration_group.add_subsystem('dummy_comp', comp)

        comp = self._create_ode((num_time_steps - 1) * num_stages)
        integration_group.add_subsystem('ode_comp', comp)
        self.connect(
            'time_comp.stage_times',
            ['.'.join(('integration_group.ode_comp', t)) for t in ode_function._time_options['paths']],
        )
        if len(static_parameters) > 0:
            self._connect_multiple(
                self._get_static_parameter_names('static_parameter_comp', 'out'),
                self._get_static_parameter_names('integration_group.ode_comp', 'paths'),
            )
        if len(dynamic_parameters) > 0:
            self._connect_multiple(
                self._get_dynamic_parameter_names('dynamic_parameter_comp', 'out'),
                self._get_dynamic_parameter_names('integration_group.ode_comp', 'paths'),
            )

        comp = VectorizedStepComp(states=states, time_units=time_units,
            num_time_steps=num_time_steps, num_stages=num_stages, num_step_vars=num_step_vars,
            glm_B=glm_B, glm_V=glm_V,
        )
        integration_group.add_subsystem('vectorized_step_comp', comp)
        self.connect('time_comp.h_vec', 'integration_group.vectorized_step_comp.h_vec')
        self._connect_multiple(
            self._get_state_names('starting_system', 'starting'),
            self._get_state_names('integration_group.vectorized_step_comp', 'y0'),
        )

        comp = VectorizedStageComp(states=states, time_units=time_units,
            num_time_steps=num_time_steps, num_stages=num_stages, num_step_vars=num_step_vars,
            glm_A=glm_A, glm_U=glm_U,
        )
        integration_group.add_subsystem('vectorized_stage_comp', comp)
        self.connect('time_comp.h_vec', 'integration_group.vectorized_stage_comp.h_vec')

        comp = VectorizedOutputComp(states=states,
            num_starting_time_steps=len(starting_norm_times), num_my_time_steps=len(my_norm_times),
            num_step_vars=num_step_vars, starting_coeffs=starting_coeffs,
        )

        promotes = []
        promotes.extend([get_name('state', state_name) for state_name in states])
        if is_starting_method:
            promotes.extend([get_name('starting', state_name) for state_name in states])

        self.add_subsystem('output_comp', comp, promotes_outputs=promotes)
        self._connect_multiple(
            self._get_state_names('integration_group.vectorized_step_comp', 'y'),
            self._get_state_names('output_comp', 'y'),
        )
        if has_starting_method:
            self._connect_multiple(
                self._get_state_names('starting_system', 'state'),
                self._get_state_names('output_comp', 'starting_state'),
            )

        src_indices_to_ode = []
        src_indices_from_ode = []
        for state_name, state in iteritems(states):
            size = np.prod(state['shape'])
            shape = state['shape']

            src_indices_to_ode.append(
                np.arange((num_time_steps - 1) * num_stages * size).reshape(
                    ((num_time_steps - 1) * num_stages,) + shape ))

            src_indices_from_ode.append(
                np.arange((num_time_steps - 1) * num_stages * size).reshape(
                    (num_time_steps - 1, num_stages,) + shape ))

        self._connect_multiple(
            self._get_state_names('integration_group.ode_comp', 'rate_path'),
            self._get_state_names('integration_group.vectorized_step_comp', 'F'),
            src_indices_from_ode,
        )
        self._connect_multiple(
            self._get_state_names('integration_group.ode_comp', 'rate_path'),
            self._get_state_names('integration_group.vectorized_stage_comp', 'F'),
            src_indices_from_ode,
        )

        self._connect_multiple(
            self._get_state_names('integration_group.vectorized_step_comp', 'y'),
            self._get_state_names('integration_group.vectorized_stage_comp', 'y'),
        )

        if formulation == 'MDF':
            self._connect_multiple(
                self._get_state_names('integration_group.vectorized_stage_comp', 'Y_out'),
                self._get_state_names('integration_group.ode_comp', 'paths'),
                src_indices_to_ode,
            )
            self._connect_multiple(
                self._get_state_names('integration_group.dummy_comp', 'Y'),
                self._get_state_names('integration_group.vectorized_stage_comp', 'Y_in'),
            )
        elif formulation == 'SAND':
            self._connect_multiple(
                self._get_state_names('integration_group.desvars_comp', 'Y'),
                self._get_state_names('integration_group.ode_comp', 'paths'),
                src_indices_to_ode,
            )
            self._connect_multiple(
                self._get_state_names('integration_group.desvars_comp', 'Y'),
                self._get_state_names('integration_group.vectorized_stage_comp', 'Y_in'),
            )
            for state_name, state in iteritems(states):
                integration_group.add_constraint('vectorized_stage_comp.Y_out:%s' % state_name, equals=0.)

        if formulation == 'MDF':
            integration_group.nonlinear_solver = NewtonSolver(iprint=2, maxiter=100)
            integration_group.linear_solver = DirectSolver()
            integration_group.jacobian = DenseJacobian()
