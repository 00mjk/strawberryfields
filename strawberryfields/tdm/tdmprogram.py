# Copyright 2019-2020 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
This module implements the :class:`.TDMProgram` class which acts as a representation for time-domain quantum circuits.
"""
# pylint: disable=too-many-instance-attributes,attribute-defined-outside-init

from operator import itemgetter
from math import ceil
import strawberryfields as sf
from strawberryfields import ops
from strawberryfields.parameters import par_is_symbolic
from strawberryfields.program_utils import CircuitError


def shift_by(l, n):
    """Convenience function to shift a list by a number of steps.

    If ``n`` is positive it shifts to the left.

    Args:
        l (list): list to be shifted
        n (int): size of the shift
    """
    return l[n:] + l[:n]


def get_modes(cmd, q):
    """Returns the registers from q required by a command.

    Args:
        cmd (.Command): a Strawberryfields command
        q (.RegRef): a register object

    Return:
        modes (tuple[int]): sequence of mode labels
    """
    reg_getter = itemgetter(*[r.ind for r in cmd.reg])
    modes = reg_getter(q)

    if not isinstance(modes, tuple):
        modes = (modes,)

    return modes


def validate_measurements(circuit, N):
    """Validate the TDM program measurements are correct.

    Args:
        circuit (list): a list containing commands or measurements specifying a circuit
        N (list): list giving the number of concurrent modes per band

    Return:
        spatial_modes (int): number of spatial modes
    """
    spatial_modes = 0

    for cmd in circuit:
        if isinstance(cmd.op, ops.Measurement):
            modes = [r.ind for r in cmd.reg]
            spatial_modes += len(modes)

    if not spatial_modes:
        raise ValueError("Must be at least one measurement.")

    if spatial_modes is not len(N):
        raise ValueError("Number of measurement operators must match number of spatial modes.")

    return spatial_modes


def input_check(args, copies):
    """Checks the input arguments have consistent dimensions.

    Args:
        args (Sequence[Sequence]): sequence of sequences specifying the value of the parameters
        copies (int): number of times the circuit should be run

    """
    # check if all lists are of equal length
    param_lengths = [len(param) for param in args]
    if len(set(param_lengths)) != 1:
        raise ValueError("Gate-parameter lists must be of equal length.")

    # check copies
    if not isinstance(copies, int) or copies < 1:
        raise TypeError("Number of copies must be a positive integer.")


def _get_mode_order(num_of_values, N):
    """Get the order by which the modes were measured"""
    all_modes = []
    for i in range(len(N)):
        ra = list(range(sum(N[:i]), sum(N[: i + 1])))
        all_modes.append(ra * ceil(max(N) / len(ra)))

    mode_order = [i for j in zip(*all_modes) for i in j]
    mode_order *= ceil(num_of_values / len(mode_order))

    return mode_order[:num_of_values]


def reshape_samples(all_samples, modes, N):
    """Reshapes the samples dict so that they have the expected correct shape.

    Corrects the :attr:`~.Results.all_samples` dictionary so that the measured modes are the ones
    defined to be measured in the circuit, instead of being spread over a larger
    number of modes due to the mode-shifting occurring in :class:`~.TDMProgram`.

    Args:
        all_samples (dict[int, list]): the raw measured samples
        modes (Sequence[int]): the modes that are measured in the circuit
        N (Sequence[int]): the number of concurrent modes per belt/spatial modes

    Returns:
        new_samples (dict[int, list]): the re-shaped samples
    """
    num_of_values = len([i for j in all_samples.values() for i in j])
    mode_order = _get_mode_order(num_of_values, N)

    # go backwards through all_samples and add them into the correct mode
    new_samples = dict()
    for i, m in enumerate(mode_order):
        idx = modes[i % len(N)]
        if idx not in new_samples:
            new_samples[idx] = []
        new_samples[idx].append(all_samples[m].pop(0))
    return new_samples


class TDMProgram(sf.Program):
    r"""Represents a photonic quantum circuit in the time domain encoding.

    The ``TDMProgam`` class provides a context manager for easily defining
    a single time-bin of the time domain algorithm. As with the standard
    :class:`~.Program`, Strawberry Fields operations are appended to the
    time domain program using the Python-embedded Blackbird syntax.

    Once created, time domain programs can be executed on Strawberry Fields'
    suite of built-in simulators in an efficient manner, or submitted
    to be executed on compatible hardware.

    Args:
        N (int or Sequence[int]): If an integer, the number of concurrent (or 'alive')
            modes in each time bin. Alternatively, a sequence of integers
            may be provided, corresponding to the number of concurrent modes in
            the possibly multiple bands in the circuit.
        name (str): the program name (optional)

    **Example**

    Below, we create a time domain program with 2 concurrent modes:

    >>> import strawberryfields as sf
    >>> from strawberryfields import ops
    >>> prog = sf.TDMProgram(N=2)

    Once created, we can construct the program using the ``prog.context()``
    context manager.

    >>> with prog.context([1, 2], [3, 4], copies=3) as (p, q):
    ...     ops.Sgate(0.7, 0) | q[1]
    ...     ops.BSgate(p[0]) | (q[0], q[1])
    ...     ops.MeasureHomodyne(p[1]) | q[0]

    Printing out this program:

    >>> prog.print()
    Sgate(0.7, 0) | (q[1])
    BSgate({p0}, 0) | (q[0], q[1])
    MeasureHomodyne({p1}) | (q[0])

    Note that ``p0`` and ``p1`` are symbolic gate parameters; to access the numeric values,
    we must use the ``prog.parameters`` attribute:

    >>> prog.parameters
    {'p0': [1, 2], 'p1': [3, 4]}

    When we simulate a time-domain program, it is first unrolled by the engine; unrolling involves
    explicitly repeating the single time-bin sequence constructed above, and *shifting* the
    simulated registers. This is performed automatically by the local engine, however, we can
    visualize the unrolling manually via the
    :meth:`~.unroll` method.

    >>> prog.unroll().print()
    Sgate(0.7, 0) | (q[1])
    BSgate(1, 0) | (q[0], q[1])
    MeasureHomodyne(3) | (q[0])
    Sgate(0.7, 0) | (q[0])
    BSgate(2, 0) | (q[1], q[0])
    MeasureHomodyne(4) | (q[1])
    Sgate(0.7, 0) | (q[1])
    BSgate(1, 0) | (q[0], q[1])
    MeasureHomodyne(3) | (q[0])
    Sgate(0.7, 0) | (q[0])
    BSgate(2, 0) | (q[1], q[0])
    MeasureHomodyne(4) | (q[1])
    Sgate(0.7, 0) | (q[1])
    BSgate(1, 0) | (q[0], q[1])
    MeasureHomodyne(3) | (q[0])
    Sgate(0.7, 0) | (q[0])
    BSgate(2, 0) | (q[1], q[0])
    MeasureHomodyne(4) | (q[1])

    Note the 'shifting' of the measured registers --- this optimization allows
    for time domain algorithms to be simulated in memory much more efficiently:

    >>> eng = sf.Engine("gaussian")
    >>> results = eng.run(prog)

    The engine automatically takes this mode shifting into account; returned samples
    will always be transformed to match the modes specified during construction:

    >>> print(results.all_samples)
    {0: [array([1.26208025]), array([1.53910032]), array([-1.29648336]),
    array([0.75743215]), array([-0.17850101]), array([-1.44751996])]}

    Note that, unlike the standard :class:`~.Program`,
    the TDM context manager has both required and essential arguments:

    * Positional arguments are used to pass sequences of gate arguments
      to apply per time-bin. Within the context, these are accessible via the ``p``
      context variable; ``p[i]`` corresponds to the ``i``-th positional
      arguments.

      All positional arguments corresponding to sequences of gate arguments
      **must be the same length**. This length determines how many time-bins
      are present in the TDM program.

      If the ``p`` variable is not used, the gate argument is assumed to be **constant**
      across all time-bins.

    * ``copies=1`` *(int)*: the number of times to repeat the time-domain program.
      For example, if a sequence of 10 gate arguments is provided, and ``copies==15``,
      then there will be a total of :math:`10\times 15` time bins in the time domain
      program. The sequence corresponding to the gate arguments is repeated ``copies``
      number of times.

    * ``shift="default"`` *(str or int)*: Defines how the qumode register is shifted at the end of
      each time bin. If set to ``"default"``, the qumode register is shifted such that each measured
      qumode reappears as a fresh mode at the beginning of the subsequent time bin. This is
      equivalent to a measured qumode being removed from the representation (by measurement) and a
      new one being added (by a light source). If set to an integer value, the register will shift
      by a step size of this integer at the end of each time bin.

    .. raw:: html

        <a class="meth-details-header collapse-header" data-toggle="collapse" href="#tutorials" aria-expanded="false" aria-controls="tutorials">
         <h2 style="font-size: 24px;">
            <i class="fas fa-angle-down rotate" style="float: right;"></i> Related tutorials
         </h2>
        </a>
        <div class="collapse" id="tutorials">

    .. customgalleryitem::
        :tooltip: Simulate massive time-domain quantum systems
        :description: :doc:`demos/run_time_domain`
        :figure: /_static/oneloop.svg

    .. raw:: html

        <div style='clear:both'></div>
        </div>
    """

    def __init__(self, N, name=None):
        # N is a list with the number of qumodes for each spatial mode
        if isinstance(N, int):
            self.N = [N]
        else:
            self.N = N
        self.concurr_modes = sum(self.N)

        super().__init__(num_subsystems=self.concurr_modes, name=name)

        self.type = "tdm"
        self.timebins = 0
        self.total_timebins = 0
        self.spatial_modes = 0
        self.measured_modes = []
        self.rolled_circuit = None
        self.unrolled_circuit = None

    # pylint: disable=arguments-differ, invalid-overridden-method
    def context(self, *args, copies=1, shift="default"):
        input_check(args, copies)
        self.copies = copies
        self.tdm_params = args
        self.shift = shift
        self.loop_vars = self.params(*[f"p{i}" for i in range(len(args))])
        return self

    def compile(self, *, device=None, compiler=None, **kwargs):
        """Compile the program given a Strawberry Fields photonic a
        hardware device specification.

        Args:
            device (~strawberryfields.api.DeviceSpec): device specification object to use for
                program compilation
            compiler (str, ~strawberryfields.compilers.Compiler): Compiler name or compile strategy
                to use. If a device is specified, this overrides the compile strategy specified by
                the hardware :class:`~.DevicSpec`.

        Keyword Args:
            optimize (bool): If True, try to optimize the program by merging and canceling gates.
                The default is False.
            warn_connected (bool): If True, the user is warned if the quantum circuit is not weakly
                connected. The default is True.

        Returns:
            Program: compiled program
        """

        import blackbird as bb

        device_layout = bb.loads(device.layout)
        # First check: the gates are in the correct order
        program_gates = [cmd.op.__class__.__name__ for cmd in self.rolled_circuit]
        device_gates = [op["op"] for op in device_layout.operations]
        if device_gates != program_gates:
            raise CircuitError(
                "Program cannot be used with the device '{}' "
                "due to incompatible topology.".format(device.target)
            )
        # Second check: the gates act in the correct modes
        program_modes = [[r.ind for r in cmd.reg] for cmd in self.rolled_circuit]
        device_modes = [op["modes"] for op in device_layout.operations]
        if program_modes != device_modes:
            raise CircuitError(
                "Program cannot be used with the device '{}' "
                "due to incompatible mode ordering.".format(device.target)
            )
        # Third check: the parameters of the gates are valid
        gate_params_ranges = device.gate_parameters
        # We will loop over the different operations in the device specification
        for i, operation in enumerate(device_layout.operations):
            # We obtain the name of the parameter(s)
            param_names = operation["args"]
            len_params_program = len(self.rolled_circuit[i].op.p)
            len_params_device = len(param_names)
            # Check if the gate has multiple parameters that all but the first one  are zero
            if len_params_device < len_params_program:
                for j in range(1, len_params_program):
                    assert self.rolled_circuit[i].op.p[j] == 0
            # Now we will check explicitly if the parameters in the program match
            counter = 0  # counts the number of symbolic variables, which are labeled consecutively by the context method
            for k, param_name in enumerate(param_names):
                # Obtain the relelvant parameter range from the device
                param_range = device.gate_parameters[param_name]
                # Obtain the value of the corresponding parameter in the program
                # If it is a numerical value check directly
                program_param = self.rolled_circuit[i].op.p[k]
                if type(program_param) == float:
                    if not program_param in param_range:
                        raise CircuitError(
                            "Program cannot be used with the device '{}' "
                            "due to incompatible parameter.".format(device.target)
                        )
                # If it is a symbolic value go and lookup its corresponding list in self.tdm_params
                else:
                    local_p_vals = self.tdm_params[counter]
                    for x in local_p_vals:
                        if not x in param_range:
                            raise CircuitError(
                                "Program cannot be used with the device '{}' "
                                "due to incompatible parameter.".format(device.target)
                            )
                    counter += 1

            # print(len(param_names))
            # print(len(self.rolled_circuit[i].op.p))
            # print(self.rolled_circuit[i].op.p)
            # for param_name in param_names:
            #    param_range = device.gate_parameters[param_name]
            # print(param_range)
        # print(self.tdm_params)
        # for op in device_layout.operations:
        #    print(op)
        # print(gate_params)
        # Note that at this point tdm allows BS on 1,0 but not on 0,1

        """
        print("list of allowed gates")
        print(list_of_gates)
        gate_params = device.gate_parameters
        print("ranges of allowed parameters")
        print(gate_params)
        print("gates passed")
        self.roll()
        print("rolled\n",self.rolled_circuit)
        gate_names =  [cmd.op.__class__.__name__ for cmd in self.rolled_circuit]
        print(gate_names)
        print("Do gates match?", gate_names == list_of_gates)
        commands = [([r.ind for r in cmd.reg], cmd.op.p[0], type(cmd.op.p[0]), cmd.op.__class__.__name__) for cmd in self.rolled_circuit]
        for x in commands:
            print(x)
        """

    def __enter__(self):
        super().__enter__()
        return self.loop_vars, self.register

    def __exit__(self, ex_type, ex_value, ex_tb):
        super().__exit__(ex_type, ex_value, ex_tb)

        if ex_type is None:
            self.spatial_modes = validate_measurements(self.circuit, self.N)
            self.timebins = len(self.tdm_params[0])
            self.total_timebins = self.timebins * self.copies
            self.rolled_circuit = self.circuit.copy()

    @property
    def parameters(self):
        return dict(zip([i.name for i in self.loop_vars], self.tdm_params))

    def roll(self):
        """Represent the program in a compressed way without rolling the for loops"""
        self.circuit = self.rolled_circuit
        return self

    def unroll(self):
        """Construct program with the register shift"""
        if self.unrolled_circuit is not None:
            self.circuit = self.unrolled_circuit
            return self

        self.circuit = []

        q = self.register

        sm = []
        for i in range(len(self.N)):
            start = sum(self.N[:i])
            stop = sum(self.N[:i]) + self.N[i]
            sm.append(slice(start, stop))

        # Above we define a list of slice intervals;
        # each slice interval corresponding to one spatial mode

        # For instance, say
        # N = [5, 4, 9, 1],
        # then this corresponds to
        # 5 concurrent modes in spatial mode A
        # 4 concurrent modes in spatial mode B
        # 9 concurrent modes in spatial mode C
        # 1 concurrent modes in spatial mode D.

        # The entries of sm will then be:
        # slice(0, 6, None)   for spatial mode A
        # slice(6, 10, None)  for spatial mode B
        # slice(10, 19, None) for spatial mode C
        # slice(19, 20, None) for spatial mode D.

        # This helps to define:
        # q[sm[0]] as concurrent modes of spatial mode A
        # q[sm[1]] as concurrent modes of spatial mode B
        # q[sm[2]] as concurrent modes of spatial mode C
        # q[sm[3]] as concurrent modes of spatial mode D.

        for cmd in self.rolled_circuit:
            if isinstance(cmd.op, ops.Measurement):
                self.measured_modes.append(cmd.reg[0].ind)

        for i in range(self.total_timebins):
            for cmd in self.rolled_circuit:
                self.apply_op(cmd, q, i)

            if self.shift == "default":
                # shift each spatial mode SEPARATELY by one step
                q_aux = list(q)
                for j in range(len(self.N)):
                    q_aux[sm[j]] = shift_by(q_aux[sm[j]], 1)
                q = tuple(q_aux)

            elif isinstance(self.shift, int):
                q = shift_by(q, self.shift)  # shift at end of each time bin

        self.unrolled_circuit = self.circuit.copy()

        return self

    def apply_op(self, cmd, q, t):
        """Apply a particular operation on register q at timestep t"""
        params = cmd.op.p.copy()

        if par_is_symbolic(params[0]):
            arg_index = int(params[0].name[1:])
            params[0] = self.tdm_params[arg_index][t % self.timebins]

        self.append(cmd.op.__class__(*params), get_modes(cmd, q))

    def assert_number_of_modes(self, device):
        if self.timebins > device.modes["temporal"]["max"]:
            raise CircuitError(
                f"This program contains {self.timebins} temporal modes, but the device '{device.target}' "
                f"only supports up to {device.modes['temporal']['max']} modes."
            )
        if self.concurr_modes > device.modes["concurrent"]:
            raise CircuitError(
                f"This program contains {self.concurr_modes} concurrent modes, but the device '{device.target}' "
                f"only supports {device.modes['concurrent']} modes."
            )
        if self.spatial_modes > device.modes["spatial"]:
            raise CircuitError(
                f"This program contains {device.timebins} temporal modes, but the device '{device.target}' "
                f"only supports up to {device.modes['max']['temporal']} modes."
            )

    def __str__(self):
        s = (
            f"<TDMProgram: concurrent modes={self.concurr_modes}, "
            f"time bins={self.total_timebins}, "
            f"spatial modes={self.spatial_modes}>"
        )
        return s
