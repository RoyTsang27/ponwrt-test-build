"""Compile the reviewed parsers and exercise malformed input without router flash."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def function(source, declaration):
    return declaration + source.split(declaration, 1)[1].split('\n}', 1)[0] + '\n}\n'


class ParserBoundsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.compiler = shlex.split(os.environ.get('CC', 'cc'))
        if not shutil.which(self.compiler[0]):
            self.skipTest('A host C compiler is required')

    def compile_run(self, source, includes=(), extra=(), args=()):
        unit = self.work / 'check.c'
        unit.write_text(source)
        binary = self.work / 'check'
        command = self.compiler + ['-std=gnu11', '-g', '-fsanitize=address,undefined',
                                   '-fno-omit-frame-pointer']
        for path in includes:
            command += ['-I', str(path)]
        result = subprocess.run(command + [str(unit)] + list(map(str, extra)) +
                                ['-o', str(binary)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(binary), *map(str, args)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_trx_bounds_and_error_cleanup(self):
        source = (ROOT / 'package/system/mtd/src/trx.c').read_text()
        header = 'struct trx_header {' + source.split('struct trx_header {', 1)[1].split('};', 1)[0] + '};\n'
        harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include <stdarg.h>
#include <sys/mman.h>
#include <arpa/inet.h>
struct mtd_info_user { uint32_t size; };
#define MEMGETINFO 1
static unsigned char area[128];
static unsigned int partition_size, opened, mapped, unmapped, closed, checksummed;
static uint32_t opt_trxmagic = 0x12345678;
static int test_ioctl(int fd, int request, struct mtd_info_user *info) {
    info->size = partition_size; return 0;
}
static int mtd_open(const char *name, bool block, bool write) { opened++; return 10; }
static void *test_mmap(void *p, size_t n, int prot, int flags, int fd, off_t off) {
    mapped++; return area;
}
static int test_munmap(void *p, size_t n) { unmapped++; return 0; }
static int test_close(int fd) { closed++; return 0; }
static int test_msync(void *p, size_t n, int flags) { return 0; }
static uint32_t crc32buf(void *p, size_t n) {
    assert(n <= partition_size - 12); checksummed++; return 0;
}
#define ioctl test_ioctl
#define mmap test_mmap
#define munmap test_munmap
#define close test_close
#define msync test_msync
'''
        harness += header + function(source, 'int\ntrx_fixup(')
        harness += r'''
int main(void) {
    struct trx_header *h = (void *)area;
    uint32_t lengths[] = {0, 1, 11, sizeof(*h)-1, sizeof(*h), 64, 65, UINT32_MAX};
    for (unsigned int i=0; i<sizeof(lengths)/sizeof(*lengths); i++) {
        memset(area, 0, sizeof(area)); partition_size=64;
        opened=mapped=unmapped=closed=checksummed=0;
        h->magic=htonl(opt_trxmagic); h->len=lengths[i];
        bool valid=h->len >= sizeof(*h) && h->len <= partition_size;
        assert(trx_fixup(1, "fixture") == (valid ? 0 : -1));
        assert(opened==1 && mapped==1 && unmapped==1 && closed==1);
        assert(checksummed==(unsigned int)valid);
    }
    opened=mapped=unmapped=closed=checksummed=0;
    h->magic=0; assert(trx_fixup(1,"fixture")==-1);
    assert(unmapped==1 && closed==1 && checksummed==0);
    for (partition_size=0; partition_size<sizeof(*h); partition_size++) {
        opened=mapped=unmapped=closed=checksummed=0;
        assert(trx_fixup(1,"fixture")==-1);
        assert(opened==0 && mapped==0 && checksummed==0);
    }
    return 0;
}
'''
        self.compile_run(harness)

    def test_ead_client_salt_prime_number_and_pong_bounds(self):
        package = ROOT / 'package/network/services/ead/src'
        source = (package / 'ead-client.c').read_text()
        harness = r'''
#include <stdio.h>
#include <assert.h>
#include <stdbool.h>
#include <string.h>
#include <arpa/inet.h>
#include "ead.h"
#include "t_pwd.h"
static char msgbuf[1500];
static struct ead_msg *msg = (void *)msgbuf;
static unsigned char saltbuf[MAXSALTLEN], bbuf[MAXPARAMLEN];
static char pw_salt[MAXSALTLEN], *username="test";
static struct t_num salt={.data=saltbuf}, B;
static uint16_t nid=0, sid;
static int auth_type=EAD_AUTH_DEFAULT;
struct t_client { int unused; };
static struct t_client client, *tc;
static struct t_preconf parameter, *tcp;
int t_getprecount(void) { return 3; }
struct t_preconf *t_getpreparam(int index) { assert(index<3); return &parameter; }
static struct t_client *t_clientopen(const char *u, struct t_num *m,
                                    struct t_num *g, struct t_num *s) {
    assert(s->len<=MAXSALTLEN); return &client;
}
'''
        for name in ('handle_prime', 'handle_b', 'handle_pong'):
            harness += function(source, 'static bool\n' + name + '(')
        harness += r'''
int main(void) {
    struct ead_msg_salt *s=EAD_DATA(msg,salt);
    for (unsigned int prime=0; prime<=255; prime++) {
        for (unsigned int len=0; len<=255; len++) {
            msg->len=htonl(sizeof(*s)); s->prime=prime; s->len=len;
            assert(handle_prime()==(prime<3 && len<=MAXSALTLEN));
        }
    }
    s->prime=0; s->len=1;
    for (unsigned int len=0; len<sizeof(*s); len++) {
        msg->len=htonl(len); assert(!handle_prime());
    }
    for (unsigned int len=0; len<=1500; len++) {
        msg->len=htonl(len);
        assert(handle_b()==(len>=sizeof(struct ead_msg_number) &&
               len-sizeof(struct ead_msg_number)<=MAXPARAMLEN));
    }
    msg->len=htonl(UINT32_MAX); assert(!handle_b());
    for (unsigned int len=0; len<=1500; len++) {
        msg->len=htonl(len);
        assert(handle_pong()==(len>sizeof(struct ead_msg_pong) &&
               len<sizeof(msgbuf)-sizeof(struct ead_msg)));
    }
    return 0;
}
'''
        self.compile_run(harness, includes=(package, package / 'tinysrp'))

    def test_nvram_malformed_regular_files_and_commit_bounds(self):
        package = ROOT / 'package/utils/nvram/src'
        if sys.platform != 'linux':
            # Only the Linux limits header and MAP_LOCKED spelling are adapted;
            # the parser, mapping/commit code and CLI CRC calculation are real.
            (self.work / 'linux').mkdir()
            (self.work / 'linux/limits.h').write_text('#include <limits.h>\n')
        harness = r'''
#include <assert.h>
#include <sys/stat.h>
#define main nvram_cli_main
#include "cli.c"
#undef main
extern size_t nvram_part_size;
int main(int argc, char **argv) {
    nvram_part_size=32768;
    nvram_handle_t *h=nvram_open(argv[1], NVRAM_RO);
    if (!h) return 2;
    assert(h->length==4096);
    assert(do_info(h)==0);
    char value[3980];
    unsigned int lengths[]={1,2,3,4,100,3900};
    for (unsigned int i=0; i<sizeof(lengths)/sizeof(*lengths); i++) {
        memset(value,'v',lengths[i]); value[lengths[i]]=0;
        assert(nvram_set(h,"checked",value)==0);
        assert(nvram_commit(h)==0);
    }
    assert(nvram_close(h)==0);
    struct stat s; assert(stat(argv[1],&s)==0 && s.st_size==4096);
    return 0;
}
'''
        import struct
        # A regular file much shorter than the nominal flash partition, with
        # a bogus header length and an unterminated variable at its exact end.
        fixture = self.work / 'nvram'
        fixture.write_bytes(struct.pack('<IIIII', 0x48534c46, 0xffffffff, 0, 0, 0) +
                            b'name=' + b'x' * (4096-25))
        flags = [] if sys.platform == 'linux' else ['-DMAP_LOCKED=0']
        self.compile_run(harness, includes=(self.work, package),
                         extra=flags + [package / 'nvram.c', package / 'crc.c'], args=(fixture,))
        for length in (0, 8, 19, 20, 24, 4095, 4096):
            with self.subTest(header_length=length):
                fixture.write_bytes(struct.pack('<IIIII', 0x48534c46, length, 0, 0, 0) +
                                    b'key=value\0\0' + b'\0' * (4096-31))
                result = subprocess.run([str(self.work / 'check'), str(fixture)],
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
