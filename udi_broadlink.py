#!/usr/bin/env python3
"""PG3 executable compatibility wrapper.

PG3 loads the executable declared in server.json (`udi_broadlink.py`).
The implementation lives in `udibroadlink.py`.
"""

from udibroadlink import main


if __name__ == '__main__':
    main()
