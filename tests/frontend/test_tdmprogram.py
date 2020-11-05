# Copyright 2020 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
r"""Unit tests for tdmprogram.py"""
import pytest
import numpy as np
import blackbird as bb
import strawberryfields as sf
from strawberryfields import ops
from strawberryfields.tdm import tdmprogram
from strawberryfields.api.devicespec import DeviceSpec
pytestmark = pytest.mark.frontend

# make test deterministic
np.random.seed(42)


def singleloop(r, alpha, phi, theta, copies, shift="default"):
    """Single delay loop with program.

    Args:
        r (float): squeezing parameter
        alpha (Sequence[float]): beamsplitter angles
        phi (Sequence[float]): rotation angles
        theta (Sequence[float]): homodyne measurement angles
        hbar (float): value in appearing in the commutation relation
    Returns:
        (list): homodyne samples from the single loop simulation
    """
    prog = tdmprogram.TDMProgram(N=2)
    with prog.context(alpha, phi, theta, copies=copies, shift=shift) as (p, q):
        ops.Sgate(r, 0) | q[1]
        ops.BSgate(p[0]) | (q[0], q[1])
        ops.Rgate(p[1]) | q[1]
        ops.MeasureHomodyne(p[2]) | q[0]
    eng = sf.Engine("gaussian")
    result = eng.run(prog)

    return result.samples[0]


def test_number_of_copies_must_be_integer():
    """Checks number of copies is integer"""
    sq_r = 1.0
    N = 3
    c = 4
    copies = 1 / 137
    alpha = [0, np.pi / 4] * c
    phi = [np.pi / 2, 0] * c
    theta = [0, 0] + [0, np.pi / 2] + [np.pi / 2, 0] + [np.pi / 2, np.pi / 2]
    with pytest.raises(TypeError, match="Number of copies must be a positive integer"):
        singleloop(sq_r, alpha, phi, theta, copies)


def test_gates_equal_length():
    """Checks gate list parameters have same length"""
    sq_r = 1.0
    N = 3
    c = 4
    copies = 10
    alpha = [0, np.pi / 4] * c
    phi = [np.pi / 2, 0] * c
    theta = [0, 0] + [0, np.pi / 2] + [np.pi / 2, 0] + [np.pi / 2]
    with pytest.raises(ValueError, match="Gate-parameter lists must be of equal length."):
        singleloop(sq_r, alpha, phi, theta, copies)


def test_at_least_one_measurement():
    """Checks circuit has at least one measurement operator"""
    sq_r = 1.0
    N = 3
    copies = 1
    alpha = [0] * 4
    phi = [0] * 4
    prog = tdmprogram.TDMProgram(N=3)
    with pytest.raises(ValueError, match="Must be at least one measurement."):
        with prog.context(alpha, phi, copies=copies, shift="default") as (p, q):
            ops.Sgate(sq_r, 0) | q[2]
            ops.BSgate(p[0]) | (q[1], q[2])
            ops.Rgate(p[1]) | q[2]
        eng = sf.Engine("gaussian")
        result = eng.run(prog)


def test_spatial_modes_number_of_measurements_match():
    """Checks number of spatial modes matches number of measurements"""
    sq_r = 1.0
    N = 3
    copies = 1
    alpha = [0] * 4
    phi = [0] * 4
    theta = [0] * 4
    with pytest.raises(
        ValueError, match="Number of measurement operators must match number of spatial modes."
    ):
        prog = tdmprogram.TDMProgram(N=[3, 3])
        with prog.context(alpha, phi, theta, copies=copies) as (p, q):
            ops.Sgate(sq_r, 0) | q[2]
            ops.BSgate(p[0]) | (q[1], q[2])
            ops.Rgate(p[1]) | q[2]
            ops.MeasureHomodyne(p[2]) | q[0]
        eng = sf.Engine("gaussian")
        result = eng.run(prog)


def test_shift_by_specified_amount():
    """Checks that shifting by 1 is equivalent to shift='end' for a program
    with one spatial mode"""
    np.random.seed(42)
    sq_r = 1.0
    N = 3
    copies = 1
    alpha = [0] * 4
    phi = [0] * 4
    theta = [0] * 4
    np.random.seed(42)
    x = singleloop(sq_r, alpha, phi, theta, copies)
    np.random.seed(42)
    y = singleloop(sq_r, alpha, phi, theta, copies, shift=1)
    assert np.allclose(x, y)


def test_str_tdm_method():
    """Testing the string method"""
    prog = tdmprogram.TDMProgram(N=1)
    assert prog.__str__() == "<TDMProgram: concurrent modes=1, time bins=0, spatial modes=0>"


def test_epr():
    """Generates an EPR state and checks that the correct correlations (noise reductions) are observed
    from the samples"""
    np.random.seed(42)
    sq_r = 1.0
    c = 2
    copies = 200

    # This will generate c EPRstates per copy. I chose c = 4 because it allows us to make 4 EPR pairs per copy that can each be measured in different basis permutations.
    alpha = [np.pi / 4, 0] * c
    phi = [0, np.pi / 2] * c

    # Measurement of 2 subsequent EPR states in XX, PP to investigate nearest-neighbour correlations in all basis permutations
    theta = [0, 0] + [np.pi / 2, np.pi / 2]  #
    x = singleloop(sq_r, alpha, phi, theta, copies)

    X0 = x[0::8]
    X1 = x[1::8]
    P2 = x[2::8]
    P3 = x[3::8]
    rtol = 5 / np.sqrt(copies)
    minusstdX1X0 = (X1 - X0).var()
    plusstdX1X0 = (X1 + X0).var()
    squeezed_std = np.exp(-2 * sq_r)
    expected_minus = sf.hbar * squeezed_std
    expected_plus = sf.hbar / squeezed_std
    assert np.allclose(minusstdX1X0, expected_minus, rtol=rtol)
    assert np.allclose(plusstdX1X0, expected_plus, rtol=rtol)

    minusstdP2P3 = (P2 - P3).var()
    plusstdP2P3 = (P2 + P3).var()
    assert np.allclose(minusstdP2P3, expected_plus, rtol=rtol)
    assert np.allclose(plusstdP2P3, expected_minus, rtol=rtol)


def test_ghz():
    """Generates a GHZ state and checks that the correct correlations (noise reductions) are observed
    from the samples
    See Eq. 5 of https://advances.sciencemag.org/content/5/5/eaaw4530
    """
    # Set up the circuit
    np.random.seed(42)
    n = 10
    vac_modes = 1
    copies = 1000
    sq_r = 5
    alpha = [np.arccos(np.sqrt(1 / (n - i + 1))) if i != n + 1 else 0 for i in range(n + vac_modes)]
    alpha[0] = 0.0
    phi = [0] * (n + vac_modes)
    phi[0] = np.pi / 2

    # Measuring X nullifier
    theta = [0] * (n + vac_modes)
    samples_X = singleloop(sq_r, alpha, phi, theta, copies)
    reshaped_samples_X = np.array(samples_X).reshape([copies, n + vac_modes])

    # We will check that the x of all the modes equal the x of the last one
    nullifier_X = lambda sample: (sample - sample[-1])[vac_modes:-1]
    val_nullifier_X = np.var([nullifier_X(x) for x in reshaped_samples_X], axis=0)
    assert np.allclose(val_nullifier_X, sf.hbar * np.exp(-2 * sq_r), rtol=5 / np.sqrt(copies))

    # Measuring P nullifier
    theta = [np.pi / 2] * (n + vac_modes)
    samples_P = singleloop(sq_r, alpha, phi, theta, copies)

    # We will check that the sum of all the p is equal to zero
    reshaped_samples_P = np.array(samples_P).reshape([copies, n + vac_modes])
    nullifier_P = lambda sample: np.sum(sample[vac_modes:])
    val_nullifier_P = np.var([nullifier_P(p) for p in reshaped_samples_P], axis=0)
    assert np.allclose(
        val_nullifier_P, 0.5 * sf.hbar * n * np.exp(-2 * sq_r), rtol=5 / np.sqrt(copies)
    )


def test_one_dimensional_cluster():
    """Test that the nullifier have the correct value in the experiment described in
    See Eq. 10 of https://advances.sciencemag.org/content/5/5/eaaw4530
    """
    np.random.seed(42)
    n = 20
    copies = 1000
    sq_r = 3
    alpha_c = np.arccos(np.sqrt((np.sqrt(5) - 1) / 2))
    alpha = [alpha_c] * n
    alpha[0] = 0.0
    phi = [np.pi / 2] * n
    theta = [0, np.pi / 2] * (n // 2)  # Note that we measure x for mode i and the p for mode i+1.
    reshaped_samples = np.array(singleloop(sq_r, alpha, phi, theta, copies)).reshape(copies, n)
    nullifier = lambda x: np.array([-x[i - 2] + x[i - 1] - x[i] for i in range(2, len(x) - 2, 2)])[
        1:
    ]
    nullifier_samples = np.array([nullifier(y) for y in reshaped_samples])
    delta = np.var(nullifier_samples, axis=0)
    assert np.allclose(delta, 1.5 * sf.hbar * np.exp(-2 * sq_r), rtol=5 / np.sqrt(copies))


def test_one_dimensional_cluster_tokyo():
    """
    One-dimensional temporal-mode cluster state as demonstrated in
    https://aip.scitation.org/doi/pdf/10.1063/1.4962732
    """
    np.random.seed(42)
    sq_r = 5
    N = 3  # concurrent modes

    n = 500  # for an n-mode cluster state
    copies = 1

    # first half of cluster state measured in X, second half in P
    theta1 = [0] * int(n / 2) + [np.pi / 2] * int(n / 2)  # measurement angles for detector A
    theta2 = theta1  # measurement angles for detector B
    prog = tdmprogram.TDMProgram(N=[1, 2])
    with prog.context(theta1, theta2, copies=copies, shift="default") as (p, q):
        ops.Sgate(sq_r, 0) | q[0]
        ops.Sgate(sq_r, 0) | q[2]
        ops.Rgate(np.pi / 2) | q[0]
        ops.BSgate(np.pi / 4) | (q[0], q[2])
        ops.BSgate(np.pi / 4) | (q[0], q[1])
        ops.MeasureHomodyne(p[0]) | q[0]
        ops.MeasureHomodyne(p[1]) | q[1]
    eng = sf.Engine("gaussian")
    result = eng.run(prog)

    xA = result.all_samples[0]
    xB = result.all_samples[1]

    X_A = xA[: n // 2]  # X samples from detector A
    P_A = xA[n // 2 :]  # P samples from detector A
    X_B = xB[: n // 2]  # X samples from detector B
    P_B = xB[n // 2 :]  # P samples from detector B

    # nullifiers defined in https://aip.scitation.org/doi/pdf/10.1063/1.4962732, Eqs. (1a) and (1b)
    ntot = len(X_A) - 1
    nX = np.array([X_A[i] + X_B[i] + X_A[i + 1] - X_B[i + 1] for i in range(ntot)])
    nP = np.array([P_A[i] + P_B[i] - P_A[i + 1] + P_B[i + 1] for i in range(ntot)])

    nXvar = np.var(nX)
    nPvar = np.var(nP)

    assert np.allclose(nXvar, 2 * sf.hbar * np.exp(-2 * sq_r), rtol=5 / np.sqrt(n))
    assert np.allclose(nPvar, 2 * sf.hbar * np.exp(-2 * sq_r), rtol=5 / np.sqrt(n))


def test_two_dimensional_cluster_denmark():
    """
    Two-dimensional temporal-mode cluster state as demonstrated in https://arxiv.org/pdf/1906.08709
    """
    np.random.seed(42)
    sq_r = 3
    delay1 = 1  # number of timebins in the short delay line
    delay2 = 12  # number of timebins in the long delay line
    n = 400  # number of timebins
    # Size of cluste is n x delay2
    # first half of cluster state measured in X, second half in P
    theta_A = [0] * int(n / 2) + [np.pi / 2] * int(n / 2)  # measurement angles for detector A
    theta_B = theta_A  # measurement angles for detector B
    # 2D cluster
    prog = tdmprogram.TDMProgram([1, delay2 + delay1 + 1])
    with prog.context(theta_A, theta_B, shift="default") as (p, q):
        ops.Sgate(sq_r, 0) | q[0]
        ops.Sgate(sq_r, 0) | q[delay2 + delay1 + 1]
        ops.Rgate(np.pi / 2) | q[delay2 + delay1 + 1]
        ops.BSgate(np.pi / 4, np.pi) | (q[delay2 + delay1 + 1], q[0])
        ops.BSgate(np.pi / 4, np.pi) | (q[delay2 + delay1], q[0])
        ops.BSgate(np.pi / 4, np.pi) | (q[delay1], q[0])
        ops.MeasureHomodyne(p[1]) | q[0]
        ops.MeasureHomodyne(p[0]) | q[delay1]
    eng = sf.Engine("gaussian")
    result = eng.run(prog)
    samples = result.all_samples

    xA = result.all_samples[0]
    xB = result.all_samples[1]

    X_A = xA[: n // 2]  # X samples from detector A
    P_A = xA[n // 2 :]  # P samples from detector A
    X_B = xB[: n // 2]  # X samples from detector B
    P_B = xB[n // 2 :]  # P samples from detector B

    # nullifiers defined in https://arxiv.org/pdf/1906.08709.pdf, Eqs. (1) and (2)
    N = delay2
    ntot = len(X_A) - delay2 - 1
    nX = np.array(
        [
            X_A[k]
            + X_B[k]
            - X_A[k + 1]
            - X_B[k + 1]
            - X_A[k + N]
            + X_B[k + N]
            - X_A[k + N + 1]
            + X_B[k + N + 1]
            for k in range(ntot)
        ]
    )
    nP = np.array(
        [
            P_A[k]
            + P_B[k]
            + P_A[k + 1]
            + P_B[k + 1]
            - P_A[k + N]
            + P_B[k + N]
            + P_A[k + N + 1]
            - P_B[k + N + 1]
            for k in range(ntot)
        ]
    )
    nXvar = np.var(nX)
    nPvar = np.var(nP)

    assert np.allclose(nXvar, 4 * sf.hbar * np.exp(-2 * sq_r), rtol=5 / np.sqrt(ntot))
    assert np.allclose(nPvar, 4 * sf.hbar * np.exp(-2 * sq_r), rtol=5 / np.sqrt(ntot))


def test_two_dimensional_cluster_tokyo():
    """
    Two-dimensional temporal-mode cluster state as demonstrated by Universtiy of Tokyo. See: https://arxiv.org/pdf/1903.03918.pdf
    """
    # temporal delay in timebins for each spatial mode
    delayA = 0
    delayB = 1
    delayC = 5
    delayD = 0
    # concurrent modes in each spatial mode
    concurrA = 1 + delayA
    concurrB = 1 + delayB
    concurrC = 1 + delayC
    concurrD = 1 + delayD

    N = [concurrA, concurrB, concurrC, concurrD]

    sq_r = 5

    # first half of cluster state measured in X, second half in P
    n = 400  # number of timebins
    theta_A = [0] * int(n / 2) + [np.pi / 2] * int(n / 2)  # measurement angles for detector A
    theta_B = theta_A  # measurement angles for detector B
    theta_C = theta_A
    theta_D = theta_A

    # 2D cluster
    prog = tdmprogram.TDMProgram(N)
    with prog.context(theta_A, theta_B, theta_C, theta_D, shift="default") as (p, q):

        ops.Sgate(sq_r, 0) | q[0]
        ops.Sgate(sq_r, 0) | q[2]
        ops.Sgate(sq_r, 0) | q[8]
        ops.Sgate(sq_r, 0) | q[9]

        ops.Rgate(np.pi / 2) | q[0]
        ops.Rgate(np.pi / 2) | q[8]

        ops.BSgate(np.pi / 4) | (q[0], q[2])
        ops.BSgate(np.pi / 4) | (q[8], q[9])
        ops.BSgate(np.pi / 4) | (q[2], q[8])
        ops.BSgate(np.pi / 4) | (q[0], q[1])
        ops.BSgate(np.pi / 4) | (q[3], q[9])

        ops.MeasureHomodyne(p[0]) | q[0]
        ops.MeasureHomodyne(p[1]) | q[1]
        ops.MeasureHomodyne(p[2]) | q[3]
        ops.MeasureHomodyne(p[3]) | q[9]

    eng = sf.Engine("gaussian")
    result = eng.run(prog)
    samples = result.all_samples

    xA = result.all_samples[0]
    xB = result.all_samples[1]
    xC = result.all_samples[3]
    xD = result.all_samples[9]

    X_A = xA[: n // 2]  # X samples from detector A
    P_A = xA[n // 2 :]  # P samples from detector A

    X_B = xB[: n // 2]  # X samples from detector B
    P_B = xB[n // 2 :]  # P samples from detector B

    X_C = xC[: n // 2]  # X samples from detector C
    P_C = xC[n // 2 :]  # P samples from detector C

    X_D = xD[: n // 2]  # X samples from detector D
    P_D = xD[n // 2 :]  # P samples from detector D

    N = delayC
    # nullifiers defined in https://arxiv.org/pdf/1903.03918.pdf, Fig. S5
    ntot = len(X_A) - N - 1
    nX1 = np.array(
        [
            X_A[k] + X_B[k] - np.sqrt(1 / 2) * (-X_A[k + 1] + X_B[k + 1] + X_C[k + N] + X_D[k + N])
            for k in range(ntot)
        ]
    )
    nX2 = np.array(
        [
            X_C[k] - X_D[k] - np.sqrt(1 / 2) * (-X_A[k + 1] + X_B[k + 1] - X_C[k + N] - X_D[k + N])
            for k in range(ntot)
        ]
    )
    nP1 = np.array(
        [
            P_A[k] + P_B[k] + np.sqrt(1 / 2) * (-P_A[k + 1] + P_B[k + 1] + P_C[k + N] + P_D[k + N])
            for k in range(ntot)
        ]
    )
    nP2 = np.array(
        [
            P_C[k] - P_D[k] + np.sqrt(1 / 2) * (-P_A[k + 1] + P_B[k + 1] - P_C[k + N] - P_D[k + N])
            for k in range(ntot)
        ]
    )

    nX1var = np.var(nX1)
    nX2var = np.var(nX2)
    nP1var = np.var(nP1)
    nP2var = np.var(nP2)

    assert np.allclose(nX1var, 2 * sf.hbar * np.exp(-2 * sq_r), rtol=5 / np.sqrt(ntot))
    assert np.allclose(nX2var, 2 * sf.hbar * np.exp(-2 * sq_r), rtol=5 / np.sqrt(ntot))
    assert np.allclose(nP1var, 2 * sf.hbar * np.exp(-2 * sq_r), rtol=5 / np.sqrt(ntot))
    assert np.allclose(nP2var, 2 * sf.hbar * np.exp(-2 * sq_r), rtol=5 / np.sqrt(ntot))


@pytest.mark.parametrize(
    "temporal_modes,concurrent_modes,spatial_modes,match",
    [
        (200, 2, 1, "contains 200 temporal modes"),
        (50, 42, 1, "contains 42 concurrent modes"),
        (50, 2, 2, "contains 2 spatial modes"),
    ],
)
def test_assert_number_of_modes(temporal_modes, concurrent_modes, spatial_modes, match):
    """Test that an exception is raised if the compiler
    is called with a device spec with an incorrect number of modes"""

    class DummyCompiler(sf.compilers.compiler.Compiler):
        """A compiler with 2 gates"""

        interactive = True
        primitives = {"S2gate", "Interferometer"}
        decompositions = set()

    device_dict = {
        "modes": {"concurrent": 2, "spatial": 1, "temporal": {"max": 100}},
        "layout": None,
        "gate_parameters": None,
        "compiler": [None],
    }
    spec = sf.api.DeviceSpec(target=None, connection=None, spec=device_dict)

    # sum of N must always be equal to number of concurrent modes, split up over
    # number of measurments/spatial modes
    N = np.array([concurrent_modes] * spatial_modes) // spatial_modes
    prog = tdmprogram.TDMProgram(N)

    params = np.ones(temporal_modes)
    with prog.context(params, params, copies=3) as (p, q):
        ops.Sgate(0.7, 0) | q[1]
        ops.BSgate(p[0]) | (q[0], q[1])
        for i in range(spatial_modes):
            ops.MeasureHomodyne(p[1]) | q[i]

    with pytest.raises(sf.program_utils.CircuitError, match=match):
        new_prog = prog.compile(device=spec, compiler=DummyCompiler())


## Test for the compilation




############################################################################
# For the test below to work, the BB cript had to be changed
# so that the squezing parameter is a dummy symbolic variable called p0
# and now the names insides the BB script match the names in the
# dictionary giving the allowed ranges for the variables
# in the DeviceSpec object
############################################################################

target = "tdm"
tm = 4
device_spec = {
    "layout": "name template_tdm\nversion 1.0\ntarget {target} (shots=1)\ntype tdm (temporal_modes={tm}, copies=1)\nfloat array p0[1, {tm}] =\n    {{rs_array}}\nfloat array p1[1, {tm}] =\n    {{bs_array}}\nfloat array p2[1, {tm}] =\n    {{r_array}}\nfloat array p3[1, {tm}] =\n    {{m_array}}\n\nSgate(p0) | 1\nBSgate(p1) | (1, 0)\nRgate(p2) | 1\nMeasureHomodyne(p3) | 0\n",
    "modes": {"concurrent": 2, "spatial": 1, "temporal": {"max": 100}},
    "compiler": ["tdm"],
    "gate_parameters": {
        "p0": [0.5643],
        "p1": [0, [0, 6.283185307179586]],
        "p2": [0, [0, 3.141592653589793], 3.141592653589793],
        "p3": [0, [0, 6.283185307179586]],
    },
}
device_spec["layout"] = device_spec["layout"].format(target=target, tm=tm)



device = DeviceSpec("tdm", device_spec, connection=None)


def test_tdm_wrong_layout():
    """Test the correct error is raised when the tdm circuit gates don't match the device spec"""
    sq_r = 0.5643
    c = 2
    copies = 10
    alpha = [np.pi / 4, 0] * c
    phi = [0, np.pi / 2] * c
    theta = [0, 0] + [np.pi / 2, np.pi / 2]
    shift = "default"
    prog = tdmprogram.TDMProgram(N=2)
    with prog.context(alpha, phi, theta, copies=copies, shift=shift) as (p, q):
        ops.Dgate(sq_r) | q[1]
        ops.BSgate(p[0]) | (q[1], q[0])
        ops.Rgate(p[1]) | q[1]
        ops.MeasureHomodyne(p[2]) | q[0]
    eng = sf.Engine("gaussian")
    with pytest.raises(sf.program_utils.CircuitError, match="The gates or the order of gates used in the Program"):
        prog.compile(device=device)


def test_tdm_wrong_modes():
    """Test the correct error is raised when the tdm circuit registers don't match the device spec"""
    sq_r = 0.5643
    c = 2
    copies = 10
    alpha = [np.pi / 4, 0] * c
    phi = [0, np.pi / 2] * c
    theta = [0, 0] + [np.pi / 2, np.pi / 2]
    shift = "default"
    prog = tdmprogram.TDMProgram(N=2)
    with prog.context(alpha, phi, theta, copies=copies, shift=shift) as (p, q):
        ops.Sgate(sq_r) | q[1]
        ops.BSgate(p[0]) | (q[0], q[1])
        ops.Rgate(p[1]) | q[1]
        ops.MeasureHomodyne(p[2]) | q[0]
    eng = sf.Engine("gaussian")
    with pytest.raises(sf.program_utils.CircuitError, match="due to incompatible mode ordering."):
        prog.compile(device=device)


def test_tdm_wrong_parameters_explicit():
    """Test the correct error is raised when the tdm circuit explicit parameters are not within the allowed ranges"""
    sq_r = 2
    c = 2
    copies = 10
    alpha = [np.pi / 4, 0] * c
    phi = [0, np.pi / 2] * c
    theta = [0, 0] + [np.pi / 2, np.pi / 2]
    shift = "default"
    prog = tdmprogram.TDMProgram(N=2)
    with prog.context(alpha, phi, theta, copies=copies, shift=shift) as (p, q):
        ops.Sgate(sq_r) | q[1]
        ops.BSgate(p[0]) | (q[1], q[0])
        ops.Rgate(p[1]) | q[1]
        ops.MeasureHomodyne(p[2]) | q[0]
    eng = sf.Engine("gaussian")
    with pytest.raises(sf.program_utils.CircuitError, match="due to incompatible parameter."):
        prog.compile(device=device)


def test_tdm_wrong_parameter_second_argument():
    """Test the correct error is raised when the tdm circuit explicit parameters are not within the allowed ranges"""
    sq_r = 0.5643
    c = 2
    copies = 10
    alpha = [np.pi / 4, 0] * c
    phi = [0, np.pi / 2] * c
    theta = [0, 0] + [np.pi / 2, np.pi / 2]
    shift = "default"
    prog = tdmprogram.TDMProgram(N=2)
    with prog.context(alpha, phi, theta, copies=copies, shift=shift) as (p, q):
        ops.Sgate(sq_r, 0.4) | q[1]
        ops.BSgate(p[0]) | (q[1], q[0])
        ops.Rgate(p[1]) | q[1]
        ops.MeasureHomodyne(p[2]) | q[0]
    eng = sf.Engine("gaussian")
    with pytest.raises(sf.program_utils.CircuitError, match="due to incompatible parameter."):
        prog.compile(device=device)


def test_tdm_wrong_parameters_symbolic():
    """Test the correct error is raised when the tdm circuit symbolic parameters are not within the allowed ranges"""
    sq_r = 0.5643
    c = 2
    copies = 200
    alpha = [137, 0] * c
    phi = [0, np.pi / 2] * c
    theta = [0, 0] + [np.pi / 2, np.pi / 2]
    shift = "default"
    prog = tdmprogram.TDMProgram(N=2)
    with prog.context(alpha, phi, theta, copies=copies, shift=shift) as (p, q):
        ops.Sgate(sq_r) | q[1]
        ops.BSgate(p[0]) | (q[1], q[0])
        ops.Rgate(p[1]) | q[1]
        ops.MeasureHomodyne(p[2]) | q[0]
    eng = sf.Engine("gaussian")
    with pytest.raises(sf.program_utils.CircuitError, match="due to incompatible parameter."):
        prog.compile(device=device)


def test_tdm_not_enough_temporal_modes():
    """Test the correct error is raised when the tdm circuit has way too many temporal modes"""
    sq_r = 0.5643
    c = 100
    copies = 1
    alpha = [0.5, 0] * c
    phi = [0, np.pi / 2] * c
    theta = [0, 0] * c
    shift = "default"
    prog = tdmprogram.TDMProgram(N=2)
    with prog.context(alpha, phi, theta, copies=copies, shift=shift) as (p, q):
        ops.Sgate(sq_r) | q[1]
        ops.BSgate(p[0]) | (q[1], q[0])
        ops.Rgate(p[1]) | q[1]
        ops.MeasureHomodyne(p[2]) | q[0]
    eng = sf.Engine("gaussian")
    with pytest.raises(
        sf.program_utils.CircuitError, match="only supports up to."
    ):
        prog.compile(device=device)
