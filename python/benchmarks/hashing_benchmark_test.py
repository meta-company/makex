"""
Benchmarking for hash functions and hashing tasks.

TODO: benchmark files of various sizes.
"""

import hashlib

# A typical hash string
DATA = """
[
'key:50a3d83a1be41eea2edf69fc4be9403e6a495902', 
'makex-file-path:aa69fe59fdec5c7a4ad8187fdc7f04fd5de66c76',
'source:967871008080618b4a359199fc5650e792cbcce0', 
'path:8377b72ecaea470e0a7fd1d66286e999e4d6931f', 
'version:development', 'environment:None', 
'makex-file:sha256:48E4A5DEBB55F543A980CE96D02472DA1EDE501C3259ED481CFCD883758DCA36:1711705496943100358_2982', 
'command:Copy:702299ae305a13a06a5382b123a973f4e1302307', 
'command:Copy:b44a6dcdba09f086123e092c694cd4d7b4e4fcd9', 
'command:Copy:0abe5dcfc6489fe4d9d09853c72ef642dccf7049', 
'command:Write:1b09b135d3e9f502f1aa96b8323ea9e65be15778', 
'require:29d8ef830de987beff17a347bf189f3d4b32d090'
]
""".encode("utf-8")

import time

def shake128(DATA):
    return hashlib.shake_128(DATA).hexdigest(32)

def shake256(DATA):
    return hashlib.shake_128(DATA).hexdigest(32)


def sha1(DATA):
    return hashlib.sha1(DATA).hexdigest()


def md5(DATA):
    return hashlib.md5(DATA).hexdigest()

#@pytest.mark.benchmark(
#    group="group-name",
#    min_time=0.1,
#    max_time=0.5,
#    min_rounds=5,
#    timer=time.time,
#    disable_gc=True,
#    warmup=False
#)
def test_bench_shake(benchmark):
    benchmark(shake128, DATA)

def test_bench_shake256(benchmark):
    benchmark(shake256, DATA)

def test_bench_md5(benchmark):
    benchmark(md5, DATA)

def test_bench_sha1(benchmark):
    benchmark(sha1, DATA)

