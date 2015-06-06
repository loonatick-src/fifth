"""
The following determines the next state of a given cell in a CAM.

The ruleset takes in a collection of rules specifying neighborhoods, as well as the configurations of
said neighborhood that yield an "on" or "off" state on the cell a ruleset is being applied to.

@date: May 31st, 2015
"""
import enum

import numpy as np


class Ruleset:
    """
    The primary class of this module, which saves configurations of cells that yield the next state.

    The ruleset will take in configurations defined by the user that specify how a cell's state should change,
    depending on the given neighborhood and current state. For example, if I have a configuration that states

    [[0, 0, 0]
    ,[1, 0, 1]
    ,[1, 1, 1]
    ]

    must match exactly for the center cell to be a 1, then each cell is checked for this configuration, and its
    state is updated afterward (note the above is merely for clarity; a configuration is not defined as such). Note
    configurations are checked until a match occurs, in order of the configurations list.
    """

    class Method(enum.Enum):
        """
        Specifies how a ruleset should be applied to a given cell.

        * A match declares that a given configuration must match exactly for a configuration to pass
        * A tolerance specifies that a configuration must match within a given percentage to pass
        * A specification allows the user to define a custom function which must return a boolean, declaring
          whether a configuration passes. This function is given a neighborhood with all necessary information.
        * Always passing allows the first configuration to always yield a success. It is redundant to add
          any additional configurations in this case (in fact it is inefficient since neighborhoods are computer
          in advance).
        """
        MATCH       = 0
        TOLERATE    = 1
        SATISFY     = 2
        ALWAYS_PASS = 3

    def __init__(self, method):
        """
        A ruleset does not begin with any configurations; only a means of verifying them.

        @method: One of the values defined in the Ruleset.Method enumeration. View class for description.
        """
        self.method = method
        self.configurations = []

    def apply_to(self, plane, *args):
        """
        Depending on the set method, applies ruleset to each cell in the plane.

        @args: If our method is TOLERATE, we pass in a value in set [0, 1]. This specifies the threshold between a
               passing (i.e. percentage of matches in a configuration is > arg) and failing. If our method is SATISFY,
               arg should be a function returning a BOOL, which takes in a current cell's value, and the
               value of its neighbors.
        """
        next_grid = []

        # Determine which function should be used to test success
        if self.method == Ruleset.Method.MATCH:
            vfunc = self._matches
        elif self.method == Ruleset.Method.TOLERATE:
            vfunc = self._tolerates
        elif self.method == Ruleset.Method.SATISFY:
            vfunc = self._satisfies
        elif self.method == Ruleset.Method.ALWAYS_PASS:
            vfunc = lambda *args: True

        # We apply our method a row at a time, to take advantage of being able to sum the totals
        # of a neighborhood in a batch manner. We try to apply a configuration to every bit of a
        # row, mark those that fail, and try the next configuration on the failed bits until
        # either all bits pass or configurations are exhausted
        for flat_index, value in enumerate(plane.grid.flat):

            next_row = bitarray(self.N)
            to_update = range(0, self.N)
            for config in self.configurations:

                next_update = []

                # After profiling with a previous version, I found that going through each index and totaling the number
                # of active states was taking much longer than I liked. Instead, we compute as many neighborhoods as possible
                # simultaneously, avoiding explicit summation via the "sum" function, at least for each state separately.
                #
                # Because the states are now represented as numbers, we instead convert each number to their binary representation
                # and add the binary representations together. We do this in chunks of 9, depending on the number of offsets, so
                # no overflowing of a single column can occur. We can then find the total of the ith neighborhood by checking the
                # sum of the ith index of the summation of every 9 chunks of numbers (this is done a row at a time).
                neighboring = []
                for flat_offset, bit_offset in config.offsets:
                    neighbor = str(plane.grid.flat[flat_index + flat_offset])
                    neighboring.append(int(neighbor[bit_offset+1:] + neighbor[:bit_offset]))

                # Chunk into groups of 9 and sum all values
                # These summations represent the total number of active states in a given neighborhood
                totals = [0] * self.N
                chunks = map(sum, [offset_totals[i:i+9] for i in range(0, len(neighboring), 9)])
                for chunk in chunks:
                    totals = list(map(sum, zip(totals, chunk)))

                # Apply change to all successful configurations
                for bit_index in to_update:
                    neighborhood = Neighborhood(flat_index, bit_index, totals[bit_index])
                    success, state = config.passes(neighborhood, vfunc, *args)
                    if success:
                        next_row[bit_index] = state
                    else:
                        next_update.append(bit_index)

                # Apply next configuration to given indices
                to_update = next_update

            # We must update all states after each next state is computed
            next_grid.append(next_row)

        # Can now apply the updates simultaneously
        for i in range(plane.grid.size):
            plane.grid.flat[i] = next_grid[i]

    def _matches(self, f_index, f_grid, indices, states):
        """
        Determines that neighborhood matches expectation exactly.

        Note this functions like the tolerate method with a tolerance of 1.
        """
        return not np.count_nonzero(f_grid[indices] ^ states)

    def _tolerates(self, f_index, f_grid, indices, states, tolerance):
        """
        Determines that neighborhood matches expectation within tolerance.

        We see that the percentage of actual matches are greater than or equal to the given tolerance level. If so, we
        consider this cell to be alive. Note tolerance must be a value 0 <= t <= 1.
        """
        non_matches = np.count_nonzero(f_grid[indices] ^ states)
        return (non_matches / len(f_grid)) >= tolerance

    def _satisfies(self, f_index, f_grid, indices, states, valid_func):
        """
        Allows custom function to relay next state of given cell.

        The passed function is supplied the list of 2-tuple elements, of which the first is a Cell and the second is
        the expected state as declared in the Neighborhood, as well as the grid and cell in question.
        """
        return valid_func(f_index, f_grid, indices, states)

