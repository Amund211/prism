"""i5: h5_cascade_ms on the i5 parse (aux text mask + letter fixes)"""

import i5_rows

i5_rows.install()

import h5_cascade_ms  # noqa: E402

i5_rows.install()  # again: modules imported by h5_cascade_ms
read_teams = h5_cascade_ms.read_teams
