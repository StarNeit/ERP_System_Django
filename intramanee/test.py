__author__ = 'peat'

# See django.test.simple.py
from django.test.simple import DjangoTestSuiteRunner
import unittest
import pkgutil
import importlib
import types
import re

pattern = re.compile('^test_')


def build_suite(package, suite):
    if isinstance(package, types.ModuleType):
        suite.addTest(unittest.defaultTestLoader.loadTestsFromModule(package))
        return

    for loader, name, is_pkg in pkgutil.walk_packages(package.__path__):
        fullname = package.__name__ + "." + name
        if is_pkg:
            build_suite(importlib.import_module(fullname), suite)
        elif pattern.match(name) is not None:
            mod = importlib.import_module(fullname)
            print(" > found " + name)
            suite.addTest(unittest.defaultTestLoader.loadTestsFromModule(mod))


class TestRunner(DjangoTestSuiteRunner):

    def __init__(self, **kwargs):
        super(TestRunner, self).__init__(1, True, True)

    def run_tests(self, test_labels, extra_tests=None, **kwargs):
        print("Testing on: %s" % test_labels)
        suite = unittest.TestSuite()
        # Discover test

        root_module = ['intramanee'] if len(test_labels) == 0 else test_labels

        for m in root_module:
            build_suite(importlib.import_module(m), suite)

        print("=" * 70)
        result = self.run_suite(suite)
        return self.suite_result(suite, result)
