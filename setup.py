#!/usr/bin/env python3

from distutils.core import setup
from catkin_pkg.python_setup import generate_distutils_setup

d = generate_distutils_setup(
    packages=['serial_motor_demo'],
    package_dir={'': 'src'},
    )

setup(**d)
