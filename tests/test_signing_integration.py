"""Exercise real host tools built from the repository's pinned packages."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = os.environ.get('PONWRT_SIGNING_TOOLS')


@unittest.skipUnless(TOOLS, 'Set PONWRT_SIGNING_TOOLS to the real host tool directory')
class JsonReleaseTests(unittest.TestCase):
    def test_nested_objects_are_freed_with_ndebug(self):
        work = Path(TOOLS).resolve().parents[1]
        source, build = work / 'json-c', work / 'json-c-build'
        compiler = shlex.split(os.environ.get('CC', 'cc'))
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            # Intercept free() in the actual release json_object.c. Recording
            # object addresses avoids counting unrelated key/buffer releases.
            unit = directory / 'check.c'
            unit.write_text('''
#include <stdlib.h>
#include <stdio.h>
#include "json_object.h"
static void *objects[66];
static unsigned int released;
void json_test_free(void *p) {
    for (unsigned int i=0; i<66; i++) if (p==objects[i]) released++;
    free(p);
}
int main(void) {
    struct json_object *root=json_object_new_object(), *current=root;
    objects[0]=root;
    for (unsigned int i=1; i<65; i++) {
        struct json_object *child=json_object_new_object();
        objects[i]=child;
        if (json_object_object_add(current,"child",child)) return 2;
        current=child;
    }
    objects[65]=json_object_new_int(42);
    if (json_object_object_add(current,"value",objects[65])) return 2;
    if (json_object_put(root)!=1) return 3;
    if (released!=66) {
        fprintf(stderr,"Released %u of 66 JSON objects\\n",released);
        return 4;
    }
    return 0;
}
''')
            obj = directory / 'json_object.o'
            result = subprocess.run(compiler + ['-std=gnu11', '-DNDEBUG', '-Dfree=json_test_free',
                                    '-I', str(source), '-I', str(build), '-c',
                                    str(source / 'json_object.c'), '-o', str(obj)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            binary = directory / 'check'
            result = subprocess.run(compiler + ['-std=gnu11', '-DNDEBUG', '-I', str(source),
                                    '-I', str(build), str(unit), str(obj),
                                    str(build / 'libjson-c.a'), '-o', str(binary)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            result = subprocess.run([str(binary)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))


@unittest.skipUnless(TOOLS, 'Set PONWRT_SIGNING_TOOLS to the real host tool directory')
class SigningIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.tools = Path(TOOLS).resolve()
        self.env = dict(os.environ, PATH=str(self.tools) + os.pathsep + os.environ['PATH'])
        self.key = self.work / 'key-build'
        self.run_tool('usign', '-G', '-s', str(self.key), '-p', str(self.key) + '.pub')
        self.run_tool('ucert', '-I', '-c', str(self.key) + '.ucert',
                      '-p', str(self.key) + '.pub', '-s', str(self.key))
        self.message = self.work / 'message'
        self.message.write_bytes(b'firmware test payload\n')
        self.signature = self.work / 'message.sig'
        self.run_tool('usign', '-S', '-m', str(self.message),
                      '-s', str(self.key), '-x', str(self.signature))

    def run_tool(self, name, *args, success=True):
        result = subprocess.run([str(self.tools / name), *args], env=self.env,
                                cwd=self.work, capture_output=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def test_append_success_and_verify(self):
        self.run_tool('ucert', '-A', '-c', str(self.key) + '.ucert', '-x', str(self.signature))
        self.run_tool('ucert', '-V', '-c', str(self.key) + '.ucert',
                      '-p', str(self.key) + '.pub', '-m', str(self.message))

    def test_append_write_failure_is_nonzero(self):
        self.run_tool('ucert', '-A', '-c', str(self.work / 'missing/cert'),
                      '-x', str(self.signature), success=False)

    def test_append_flush_failure_is_nonzero(self):
        if not Path('/dev/full').exists():
            self.skipTest('Linux /dev/full is required')
        self.run_tool('ucert', '-A', '-c', '/dev/full', '-x', str(self.signature), success=False)

    def test_short_signature_is_rejected(self):
        self.signature.write_bytes(b'truncated')
        self.run_tool('ucert', '-A', '-c', str(self.key) + '.ucert',
                      '-x', str(self.signature), success=False)

    def test_real_image_recipes_and_release_verification(self):
        source = (ROOT / 'include/image-commands.mk').read_text()
        images = self.work / 'images'
        images.mkdir()
        recipes = ('append-metadata', 'append-gl-metadata')
        targets = ('images/test-sysupgrade.bin', 'images/test-sysupgrade.itb')
        makefile = 'CONFIG_SIGN_FIRMWARE=y\nBUILD_KEY=key-build\nSUPPORTED_DEVICES=test\n'
        makefile += "metadata_json='{\"metadata_version\":\"1.1\"}'\nmetadata_gl_json='{\"metadata_version\":\"1.1\"}'\n"
        for name in recipes:
            body = source.split('define Build/' + name + '\n', 1)[1].split('\nendef', 1)[0]
            makefile += 'define Build/' + name + '\n' + body + '\nendef\n'
        makefile += '.PHONY: all\nall: ' + ' '.join(targets) + '\n'
        for target, recipe in zip(targets, recipes):
            makefile += target + ':\n\tprintf "firmware test payload\\n" > "$@"\n\t$(Build/' + recipe + ')\n'
        (self.work / 'Makefile').write_text(makefile)
        result = subprocess.run(['make'], cwd=self.work, env=self.env, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        (self.work / 'staging_dir/host').mkdir(parents=True)
        (self.work / 'staging_dir/host/bin').symlink_to(self.tools, target_is_directory=True)
        command = ['bash', str(ROOT / 'scripts/verify-release.sh'), 'images']
        # A fresh CI step does not inherit OpenWrt make's host-tool PATH.
        verify_env = dict(self.env, PATH=os.defpath)
        verified = subprocess.run(command, cwd=self.work, env=verify_env, capture_output=True)
        self.assertEqual(verified.returncode, 0, verified.stderr.decode(errors='replace'))
        self.assertIn(b'Verified 2 signed', verified.stdout)
        with (self.work / targets[1]).open('r+b') as stream:
            stream.write(b'TAMPERED')
        tampered = subprocess.run(command, cwd=self.work, env=verify_env, capture_output=True)
        self.assertNotEqual(tampered.returncode, 0)


if __name__ == '__main__':
    unittest.main()
