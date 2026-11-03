"""The Mac shader libraries' deployment target (dm/mac/min_os.mk).

Regression for one black screen on every Mac older than the packing one: `xcrun metal` without -mmacosx-version-min took the selected SDK's target, so the libraries carried MSL 4.1
and a minimum of macOS 27; a Mac on 26.6 refused every one of them ("This library is using language version 4.1 which is not supported on this OS"), the host has no run-time fallback,
and the game presented nothing. The iOS compile convention always had -mios-version-min; this is the macOS counterpart.

No Metal compiler and no game files: these read the sources and the one file that states the minimum.
"""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / 'dm/gfx/tools'


def read(name):
    return (TOOLS / name).read_text(encoding='utf-8')


def macos_min_from_mk():
    line = re.search(r'^MACOS_MIN\s*:?=\s*(\S+)', (REPO / 'dm/mac/min_os.mk').read_text(encoding='utf-8'), re.M)
    return line.group(1)


class MacDeploymentTarget(unittest.TestCase):

    def test_metal_compile_passes_the_minimum(self):
        """The macOS compile line must carry -mmacosx-version-min, as the iOS one carries -mios-version-min."""
        src = read('dmsh_build.py')
        line = next(l for l in src.splitlines() if l.startswith('MAC_METAL ='))
        self.assertIn('-mmacosx-version-min=', line)

    def test_ios_has_its_counterpart(self):
        """Guards the claim in the note above: iOS is the working reference, not the thing being changed."""
        self.assertIn('-mios-version-min=', (REPO / 'dm/ios/tools/ios_metal.py').read_text(encoding='utf-8'))

    def test_minimum_comes_from_min_os_mk(self):
        """One statement of the minimum: dm/mac/min_os.mk, which the host's Makefile and pack_app.py already follow."""
        src = read('dmsh_build.py')
        self.assertIn('macos_min()', src)
        minmk = (REPO / 'dm/mac/min_os.mk').read_text(encoding='utf-8')
        self.assertRegex(minmk, r'(?m)^MACOS_MIN\s*:?=')

    def test_minimum_is_not_taken_from_this_mac(self):
        """The bug itself: the value must not come from sw_vers (this Mac's system) in the shader build."""
        src = read('dmsh_build.py')
        block = src[src.index('MAC_MIN'):src.index('MAC_RECORD')]
        self.assertNotIn('sw_vers', block)

    def test_the_minimum_is_in_the_compile_record(self):
        """MAC_RECORD is what the compile cache keys on: a change of the minimum must invalidate the libraries, not reuse them."""
        src = read('dmsh_build.py')
        line = next(l for l in src.splitlines() if l.startswith('MAC_RECORD ='))
        self.assertIn('MAC_METAL', line)

    def test_the_minimum_is_part_of_the_chain_version(self):
        """b-<V> is named after the chain version: the minimum has to be in V, or a build would reuse libraries made for another one."""
        src = read('dmsh_chain.py')
        version = src[src.index('def version('):src.index('def code_form')]
        self.assertIn('macos_min()', version)


class MacosMinReader(unittest.TestCase):
    """dmsh_chain.macos_min() reads the one file, with comments and either assignment operator.

    The file is stubbed rather than written to disk: this proves the parsing, and it does not depend on a writable scratch directory (a sandbox may refuse one).
    """

    def reader(self, text):
        # The reader only needs GFX (two levels up from dm/gfx/tools) and open(): run its source with both supplied.
        src = read('dmsh_chain.py')
        start = src.index('def macos_min():')
        end = src.index('def options():')
        body = src[start:end]

        def fake_open(path, *a, **kw):
            import io
            return io.StringIO(text)

        ns = {'os': os, 'GFX': 'irrelevant', 'open': fake_open}
        exec(body, ns)
        return ns['macos_min']

    def test_comment_and_trailing_comment(self):
        fn = self.reader('# the minimum\nMACOS_MIN := 26.6\n')
        self.assertEqual(fn(), '26.6')

    def test_plain_equals(self):
        fn = self.reader('MACOS_MIN = 26.7\n')
        self.assertEqual(fn(), '26.7')

    def test_the_repository_value_parses(self):
        fn = self.reader((REPO / 'dm/mac/min_os.mk').read_text(encoding='utf-8'))
        self.assertEqual(fn(), macos_min_from_mk())

    def test_missing_key_is_an_error(self):
        fn = self.reader('# nothing here\nOTHER := 1\n')
        with self.assertRaises(SystemExit):
            fn()


class PsoArchiveDefault(unittest.TestCase):

    def test_macos_default_is_the_libraries_minimum(self):
        """The app's pipeline archive must name the same minimum as its libraries, not this Mac's system."""
        src = read('pso_offline.py')
        body = src[src.index('def os_min_default'):src.index('def main')]
        self.assertIn('dmsh_chain.macos_min()', body)
        self.assertNotIn("'sw_vers'", body)

    def test_ios_keeps_the_sdk(self):
        src = read('pso_offline.py')
        body = src[src.index('def os_min_default'):src.index('def main')]
        self.assertIn('--show-sdk-version', body)


if __name__ == '__main__':
    unittest.main()
